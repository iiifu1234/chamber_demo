"""
Instrument API Layer (儀器端 API 服務與資料傳送器)
負責：
1. 從儀器硬體或虛擬艙 (BaseChamber / ChamberController) 擷取即時量測資料 (Telemetry)
2. 透過 HTTP REST API 將儀器資料主動傳送 (POST) 至 Web UI 伺服器的 API 接口 (/api/telemetry)
3. 接收來自 Web UI API 回傳或下發的控制指令並於儀器端執行
4. 提供獨立的儀器端 REST API 介面 (/instrument/...) 供外部系統直接讀寫儀器
"""

import asyncio
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Callable
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from commands.controller import ChamberController

logger = logging.getLogger("InstrumentAPI")


class InstrumentCommandPayload(BaseModel):
    action: str
    value: Optional[Any] = None
    temp: Optional[float] = None
    humi: Optional[float] = None
    project: Optional[str] = None
    engineer: Optional[str] = None
    start_time: Optional[str] = None
    duration: Optional[str] = None
    name: Optional[str] = None
    operator: Optional[str] = None
    total_hours: Optional[float] = None


class InstrumentAPIClient:
    """
    儀器端 API 傳送器 (Instrument-to-WebUI API Transmitter)
    將儀器端的即時數據打包成標準 JSON，傳送到 Web UI 的 API 接口 (POST /api/telemetry)
    """

    def __init__(
        self,
        controller: Optional[ChamberController] = None,
        web_ui_api_url: str = "http://127.0.0.1:8000",
        push_interval_sec: float = 0.25,
        source_id: str = "instrument-node-01",
    ):
        self.controller = controller or ChamberController()
        self.web_ui_api_url = web_ui_api_url.rstrip("/")
        self.push_interval_sec = push_interval_sec
        self.source_id = source_id

        self.running = False
        self.push_count = 0
        self.last_push_time: Optional[str] = None
        self.last_error: Optional[str] = None

        # Optional in-process handler when running embedded inside Web UI Server
        self._local_ingest_callback: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None

    def set_local_ingest_callback(self, callback: Callable[[Dict[str, Any]], List[Dict[str, Any]]]):
        """設定同行程內嵌 API 接收器 (避免本機迴路延遲，同時保留完整 HTTP API 架構)"""
        self._local_ingest_callback = callback

    def collect_payload(self) -> Dict[str, Any]:
        """從所有儀器收集最新遙測數據並封裝為 API 傳輸格式"""
        chambers_data = self.controller.get_all_telemetry_dict()
        return {
            "source_id": self.source_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "chambers": chambers_data,
        }

    def push_telemetry_http(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """透過 HTTP POST 將儀器資料傳送到 Web UI 的 /api/telemetry 接口"""
        if payload is None:
            payload = self.collect_payload()

        url = f"{self.web_ui_api_url}/api/telemetry"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "X-Instrument-Source": self.source_id},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                self.push_count += 1
                self.last_push_time = time.strftime("%H:%M:%S")
                self.last_error = None

                # 若 Web UI API 有排隊等待執行的遠端控制指令，立即在儀器端執行
                pending_cmds = resp_data.get("pending_commands", [])
                for cmd_item in pending_cmds:
                    cid = cmd_item.get("chamber_id", "chamber-1")
                    self.controller.execute_action(cid, cmd_item)

                return resp_data
        except Exception as e:
            self.last_error = str(e)
            raise

    def push_single_chamber_http(self, chamber_id: str) -> Dict[str, Any]:
        """透過 HTTP POST 將單一台儀器數據傳送到 Web UI 的 /api/chambers/{chamber_id}/telemetry 接口"""
        telemetry_dict = self.controller.get_telemetry(chamber_id).to_api_dict()
        url = f"{self.web_ui_api_url}/api/chambers/{chamber_id}/telemetry"
        body = json.dumps({
            "source_id": self.source_id,
            "telemetry": telemetry_dict,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "X-Instrument-Source": self.source_id},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            self.push_count += 1
            self.last_push_time = time.strftime("%H:%M:%S")
            self.last_error = None
            for cmd_item in resp_data.get("pending_commands", []):
                self.controller.execute_action(chamber_id, cmd_item)
            return resp_data

    async def start_push_loop(self, use_http: bool = True):
        """啟動背景定時推送任務，持續將儀器資料傳送至 Web UI API"""
        self.running = True
        logger.info(
            f"[InstrumentAPI] 啟動儀器資料傳送服務 -> 目標 Web UI API: {self.web_ui_api_url}/api/telemetry"
        )
        while self.running:
            await asyncio.sleep(self.push_interval_sec)
            try:
                payload = self.collect_payload()
                if use_http and self._local_ingest_callback is None:
                    await asyncio.to_thread(self.push_telemetry_http, payload)
                elif self._local_ingest_callback is not None:
                    pending_cmds = self._local_ingest_callback(payload)
                    self.push_count += 1
                    self.last_push_time = time.strftime("%H:%M:%S")
                    self.last_error = None
                    for cmd_item in pending_cmds:
                        cid = cmd_item.get("chamber_id", "chamber-1")
                        self.controller.execute_action(cid, cmd_item)
            except Exception as e:
                self.last_error = str(e)


def create_instrument_api_app(
    web_ui_api_url: str = "http://127.0.0.1:8000",
    push_interval_sec: float = 0.25,
) -> FastAPI:
    """
    建立獨立的「儀器端 API 伺服器」 (預設可運行於 Port 8001)
    - 對外提供儀器原生 API (/instrument/...)
    - 背景自動透過 InstrumentAPIClient 將資料 POST 到 Web UI 的 /api/telemetry 接口
    """
    inst_app = FastAPI(title="Chamber Instrument API Service (儀器端 API 服務)")
    client = InstrumentAPIClient(
        web_ui_api_url=web_ui_api_url,
        push_interval_sec=push_interval_sec,
        source_id="external-instrument-api",
    )

    @inst_app.on_event("startup")
    async def on_startup():
        asyncio.create_task(client.start_push_loop(use_http=True))

    @inst_app.get("/instrument/status")
    async def get_instrument_status():
        return {
            "service": "Chamber Instrument API",
            "source_id": client.source_id,
            "target_web_ui_api": f"{client.web_ui_api_url}/api/telemetry",
            "push_count": client.push_count,
            "last_push_time": client.last_push_time,
            "last_error": client.last_error,
            "chambers": list(client.controller.chambers.keys()),
        }

    @inst_app.get("/instrument/chambers")
    async def get_all_chambers_telemetry():
        return client.collect_payload()

    @inst_app.get("/instrument/chambers/{chamber_id}/telemetry")
    async def get_chamber_telemetry(chamber_id: str):
        if chamber_id not in client.controller.chambers:
            raise HTTPException(status_code=404, detail=f"Chamber '{chamber_id}' not found")
        return {
            "chamber_id": chamber_id,
            "telemetry": client.controller.get_telemetry(chamber_id).to_api_dict(),
        }

    @inst_app.post("/instrument/chambers/{chamber_id}/command")
    async def send_instrument_command(chamber_id: str, payload: InstrumentCommandPayload):
        if chamber_id not in client.controller.chambers:
            raise HTTPException(status_code=404, detail=f"Chamber '{chamber_id}' not found")
        result = client.controller.execute_action(chamber_id, payload.model_dump(exclude_none=True))
        # 立即將更新後的狀態推送至 Web UI API
        try:
            await asyncio.to_thread(client.push_single_chamber_http, chamber_id)
        except Exception:
            pass
        return result

    @inst_app.post("/instrument/push-now")
    async def trigger_manual_push():
        """立即手動觸發一次將所有儀器數據 POST 到 Web UI API"""
        try:
            resp = await asyncio.to_thread(client.push_telemetry_http)
            return {"status": "pushed", "web_ui_response": resp}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to push to Web UI API: {e}")

    return inst_app
