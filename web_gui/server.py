"""
Multi-Chamber Web GUI Server & REST API Hub (FastAPI + REST API + WebSocket)
架構設計：
1. Web UI API 接口 (/api/...):
   - POST /api/telemetry                      : 接收「儀器端 API」傳送過來的多機台即時資料
   - POST /api/chambers/{chamber_id}/telemetry: 接收「儀器端 API」傳送過來的單機台即時資料
   - GET  /api/telemetry                      : 提供 Web UI 介面透過 REST API 讀取並顯示所有機台資料 (Show Data)
   - GET  /api/chambers/{chamber_id}/telemetry: 提供 Web UI 介面讀取單一機台即時與歷史資料
   - POST /api/chambers/{chamber_id}/command  : 提供 Web UI 介面下達控制指令並轉發給儀器端 API
   - GET  /api/status                         : 查詢儀器 API 與 Web UI API 的連線與資料傳輸狀態
2. WebSocket 即時推播 (/ws):
   - 當 Web UI API 收到儀器傳來的資料時，自動推播至前端 Web UI 畫面即時更新。
"""

import os
import json
import time
import asyncio
from typing import Set, Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from chamber.base import STATE_METADATA, ChamberState
from chamber.instrument_api import InstrumentAPIClient
from commands.controller import ChamberController

app = FastAPI(
    title="Multi-Chamber Web UI & Telemetry API Server",
    description="Web UI 介面與 API 資料接收/展示中心 (接收來自儀器 API 的遙測數據並顯示於前端)",
    version="2.0.0",
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
TEMPLATE_PATH = os.path.join(CURRENT_DIR, "templates", "index.html")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ======================= Web UI API 資料儲存與狀態中心 =======================
class WebUITelemetryStore:
    """儲存由「儀器端 API」傳送至 Web UI API 的即時數據與待執行指令佇列"""

    def __init__(self):
        self.chambers_data: Dict[str, Dict[str, Any]] = {}
        self.history_data: Dict[str, List[Dict[str, Any]]] = {}
        self.max_history_len = 150

        # 待傳回給外部儀器端 API 執行的控制指令佇列
        self.pending_commands: List[Dict[str, Any]] = []

        # API 傳輸統計資訊
        self.total_api_packets_received: int = 0
        self.last_source_id: str = "initializing"
        self.last_received_timestamp: str = "--:--:--"
        self.last_external_push_epoch: float = 0.0

    def update_chamber(self, chamber_id: str, data: Dict[str, Any], source_id: str = "instrument-api"):
        """更新單一機台遙測數據並寫入歷史紀錄"""
        # 補齊預設欄位以支援外部儀器精簡 JSON 格式傳入
        state_code = int(data.get("state", 2))
        try:
            st_enum = ChamberState(state_code)
        except ValueError:
            st_enum = ChamberState.RUNNING
        default_st_text, default_st_color = STATE_METADATA[st_enum]

        now_str = time.strftime("%H:%M:%S")
        normalized = {
            "time": data.get("time") or data.get("timestamp") or now_str,
            "temp_pv": round(float(data.get("temp_pv", 25.0)), 2),
            "temp_sv": round(float(data.get("temp_sv", 60.0)), 2),
            "humi_pv": round(float(data.get("humi_pv", 55.0)), 2),
            "humi_sv": round(float(data.get("humi_sv", 75.0)), 2),
            "state": state_code,
            "state_text": data.get("state_text", default_st_text),
            "state_color": data.get("state_color", default_st_color),
            "heater": bool(data.get("heater", False)),
            "cooler": bool(data.get("cooler", False)),
            "humidifier": bool(data.get("humidifier", False)),
            "dehumidifier": bool(data.get("dehumidifier", False)),
            "door_open": bool(data.get("door_open", False)),
            "uptime": data.get("uptime") or data.get("uptime_str") or "00:00:00",
            "sim_speed": float(data.get("sim_speed", 1.0)),
            "test_name": data.get("test_name", "Instrument API Active Test"),
            "test_operator": data.get("test_operator", "Reliability Lab"),
            "test_remaining_str": data.get("test_remaining_str", "04h 00m 00s"),
            "test_progress_pct": float(data.get("test_progress_pct", 50.0)),
            "est_completion_time": data.get("est_completion_time", "Today"),
            "next_available_slot": data.get("next_available_slot", "Available after test"),
            "bookings": data.get("bookings", []),
            "source_id": source_id,
        }

        self.chambers_data[chamber_id] = normalized

        if chamber_id not in self.history_data:
            self.history_data[chamber_id] = []
        self.history_data[chamber_id].append({
            "time": normalized["time"],
            "temp_pv": normalized["temp_pv"],
            "temp_sv": normalized["temp_sv"],
            "humi_pv": normalized["humi_pv"],
            "humi_sv": normalized["humi_sv"],
            "state": normalized["state"],
        })
        if len(self.history_data[chamber_id]) > self.max_history_len:
            self.history_data[chamber_id].pop(0)

    def ingest_bulk(self, payload: Dict[str, Any], is_external_http: bool = False) -> List[Dict[str, Any]]:
        """接收儀器端 API 傳來的整批資料並回傳待執行指令"""
        source_id = payload.get("source_id", "instrument-api")
        chambers = payload.get("chambers", {})
        for cid, cdata in chambers.items():
            # 若已有現行 bookings 且外部傳入未帶 bookings，保留既有預約
            if "bookings" not in cdata and cid in self.chambers_data:
                cdata["bookings"] = self.chambers_data[cid].get("bookings", [])
            self.update_chamber(cid, cdata, source_id=source_id)

        self.total_api_packets_received += 1
        self.last_source_id = source_id
        self.last_received_timestamp = time.strftime("%H:%M:%S")
        if is_external_http:
            self.last_external_push_epoch = time.time()

        cmds = list(self.pending_commands)
        self.pending_commands.clear()
        return cmds

    def pop_commands_for_chamber(self, chamber_id: str) -> List[Dict[str, Any]]:
        matched = [c for c in self.pending_commands if c.get("chamber_id") == chamber_id]
        self.pending_commands = [c for c in self.pending_commands if c.get("chamber_id") != chamber_id]
        return matched

    def get_api_status(self) -> Dict[str, Any]:
        return {
            "connected": len(self.chambers_data) > 0,
            "source_id": self.last_source_id,
            "last_received_time": self.last_received_timestamp,
            "total_packets": self.total_api_packets_received,
            "active_chambers": list(self.chambers_data.keys()),
            "endpoints": {
                "instrument_push_bulk": "POST /api/telemetry",
                "instrument_push_single": "POST /api/chambers/{chamber_id}/telemetry",
                "webui_get_all_data": "GET /api/telemetry",
                "webui_get_chamber_data": "GET /api/chambers/{chamber_id}/telemetry",
                "webui_send_command": "POST /api/chambers/{chamber_id}/command",
            },
        }


telemetry_store = WebUITelemetryStore()
active_websockets: Set[WebSocket] = set()

# 內建儀器控制器與儀器 API 傳送端 (確保單一啟動時也透過 InstrumentAPIClient 傳送數據至 Web UI API)
local_controller = ChamberController()
instrument_api_client = InstrumentAPIClient(
    controller=local_controller,
    source_id="instrument-api-client",
    push_interval_sec=0.2,
)


def _local_instrument_ingest_bridge(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    當外部獨立儀器行程 (external-instrument-api) 正在透過 HTTP POST 推送時，
    內建模擬傳送器自動禮讓；否則由內建 InstrumentAPIClient 持續推送資料至 Web UI Store。
    """
    if time.time() - telemetry_store.last_external_push_epoch < 3.0:
        return []
    return telemetry_store.ingest_bulk(payload, is_external_http=False)


instrument_api_client.set_local_ingest_callback(_local_instrument_ingest_bridge)

# 初始化首筆資料，讓 GET /api/telemetry 一啟動即有完整數據
telemetry_store.ingest_bulk(instrument_api_client.collect_payload(), is_external_http=False)


async def broadcast_latest_to_websockets():
    """將 Web UI API 儲存的最新資料推播給所有連線中的瀏覽器"""
    if not active_websockets or not telemetry_store.chambers_data:
        return

    payload = json.dumps({
        "type": "telemetry_multi",
        "api_status": telemetry_store.get_api_status(),
        "chambers": telemetry_store.chambers_data,
    })

    stale = []
    for ws in active_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        active_websockets.discard(ws)


# ======================= 1. Web UI 頁面路由 =======================
@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ======================= 2. 儀器端 API -> Web UI API 接收接口 =======================
@app.post("/api/telemetry")
async def receive_bulk_telemetry_from_instrument(request: Request):
    """
    [儀器 API -> Web UI API 接口 (多機台批次)]
    接收來自儀器端 (InstrumentAPIClient 或外部實體儀器) 傳送過來的 JSON 數據：
    格式範例:
    {
      "source_id": "instrument-node-01",
      "chambers": {
        "chamber-1": { "temp_pv": 85.0, "temp_sv": 85.0, "humi_pv": 85.0, "humi_sv": 85.0, "state": 2, ... }
      }
    }
    """
    body = await request.json()
    pending_cmds = telemetry_store.ingest_bulk(body, is_external_http=True)
    await broadcast_latest_to_websockets()
    return {
        "status": "ok",
        "received_chambers": list(body.get("chambers", {}).keys()),
        "total_packets": telemetry_store.total_api_packets_received,
        "pending_commands": pending_cmds,
    }


@app.post("/api/chambers/{chamber_id}/telemetry")
async def receive_single_chamber_telemetry(chamber_id: str, request: Request):
    """
    [儀器 API -> Web UI API 接口 (單一機台)]
    讓個別儀器直接 POST 溫濕度與狀態數據到 Web UI：
    支援兩種格式：
    1. {"source_id": "inst-1", "telemetry": {"temp_pv": 65.2, "humi_pv": 70.1, ...}}
    2. 直接傳入欄位 {"temp_pv": 65.2, "temp_sv": 85.0, "humi_pv": 70.1, "humi_sv": 85.0, "state": 2, ...}
    """
    body = await request.json()
    source_id = body.get("source_id", request.headers.get("X-Instrument-Source", f"inst-{chamber_id}"))
    telemetry_data = body.get("telemetry", body)

    # 若既有該機台的設定資訊且外部僅傳送核心感測數值，自動合併既有欄位
    existing = dict(telemetry_store.chambers_data.get(chamber_id, {}))
    existing.update(telemetry_data)

    telemetry_store.update_chamber(chamber_id, existing, source_id=source_id)
    telemetry_store.total_api_packets_received += 1
    telemetry_store.last_source_id = source_id
    telemetry_store.last_received_timestamp = time.strftime("%H:%M:%S")
    telemetry_store.last_external_push_epoch = time.time()

    # 同步更新本地控制器數值，保持狀態一致
    if chamber_id in local_controller.chambers:
        ch = local_controller.get_chamber(chamber_id)
        if "temp_pv" in telemetry_data:
            ch.current_temp = float(telemetry_data["temp_pv"])
        if "temp_sv" in telemetry_data:
            ch.target_temp = float(telemetry_data["temp_sv"])
        if "humi_pv" in telemetry_data:
            ch.current_humi = float(telemetry_data["humi_pv"])
        if "humi_sv" in telemetry_data:
            ch.target_humi = float(telemetry_data["humi_sv"])

    await broadcast_latest_to_websockets()
    pending_cmds = telemetry_store.pop_commands_for_chamber(chamber_id)
    return {
        "status": "ok",
        "chamber_id": chamber_id,
        "telemetry": telemetry_store.chambers_data[chamber_id],
        "pending_commands": pending_cmds,
    }


# ======================= 3. Web UI 介面 -> 讀取與顯示資料 API (Show Data) =======================
@app.get("/api/status")
async def get_api_connection_status():
    """取得 Web UI API 與儀器 API 的連線狀態與統計資訊"""
    return telemetry_store.get_api_status()


@app.get("/api/telemetry")
async def get_all_telemetry_for_webui():
    """
    [Web UI Show Data API]
    提供 Web UI 前端透過 HTTP GET 取得所有機台最新資料與 API 狀態
    """
    return {
        "type": "telemetry_multi",
        "api_status": telemetry_store.get_api_status(),
        "chambers": telemetry_store.chambers_data,
    }


@app.get("/api/chambers/{chamber_id}/telemetry")
async def get_single_chamber_telemetry_for_webui(chamber_id: str):
    """
    [Web UI Show Data API - 單一機台含歷史曲線資料]
    """
    if chamber_id not in telemetry_store.chambers_data:
        raise HTTPException(status_code=404, detail=f"Chamber '{chamber_id}' not found")
    return {
        "chamber_id": chamber_id,
        "api_status": telemetry_store.get_api_status(),
        "telemetry": telemetry_store.chambers_data[chamber_id],
        "history": telemetry_store.history_data.get(chamber_id, []),
    }


# ======================= 4. Web UI 介面 -> 下達控制指令 API =======================
@app.post("/api/chambers/{chamber_id}/command")
async def post_chamber_command_from_webui(chamber_id: str, request: Request):
    """
    [Web UI 控制指令 API]
    Web UI 介面透過 REST API 發送控制指令 (如開關機、設定溫濕度 SV、開關門、預約機台)，
    指令會：
    1. 排入 pending_commands 佇列，當外部儀器 API 下次傳送資料時回傳給儀器執行
    2. 同步在內建儀器控制器上執行並立即更新 Web UI 狀態
    """
    cmd = await request.json()
    cmd["chamber_id"] = chamber_id

    # 1. 排入外部儀器指令佇列
    telemetry_store.pending_commands.append(cmd)

    # 2. 同步於本地控制器執行並立即反映在資料儲存區
    res = local_controller.execute_action(chamber_id, cmd)
    if res.get("status") == "ok" and "telemetry" in res:
        telemetry_store.update_chamber(
            chamber_id,
            res["telemetry"],
            source_id=telemetry_store.last_source_id,
        )
        await broadcast_latest_to_websockets()

    return {
        "status": "ok",
        "chamber_id": chamber_id,
        "command": cmd,
        "telemetry": telemetry_store.chambers_data.get(chamber_id),
    }


@app.get("/api/commands/pending")
async def get_pending_commands(chamber_id: Optional[str] = None):
    """供外部儀器端 API 主動輪詢待執行的控制指令"""
    if chamber_id:
        cmds = telemetry_store.pop_commands_for_chamber(chamber_id)
    else:
        cmds = list(telemetry_store.pending_commands)
        telemetry_store.pending_commands.clear()
    return {"status": "ok", "pending_commands": cmds}


# ======================= 5. WebSocket 即時雙向通道 =======================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        # 連線成功時立即發送一次當前 API 資料
        await websocket.send_text(json.dumps({
            "type": "telemetry_multi",
            "api_status": telemetry_store.get_api_status(),
            "chambers": telemetry_store.chambers_data,
        }))

        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            cid = cmd.get("chamber_id", "chamber-1")
            telemetry_store.pending_commands.append(cmd)
            res = local_controller.execute_action(cid, cmd)
            if res.get("status") == "ok" and "telemetry" in res:
                telemetry_store.update_chamber(cid, res["telemetry"], source_id=telemetry_store.last_source_id)
                await broadcast_latest_to_websockets()

    except WebSocketDisconnect:
        active_websockets.discard(websocket)
    except Exception:
        active_websockets.discard(websocket)


async def periodic_ws_broadcast_loop():
    """定時將儀器 API 送達 Web UI API 的最新資料同步至前端畫面"""
    while True:
        await asyncio.sleep(0.2)
        await broadcast_latest_to_websockets()


@app.on_event("startup")
async def startup_event():
    # 若未停用內建儀器傳送端，啟動 InstrumentAPIClient 定時傳送數據至 Web UI Store
    if os.environ.get("DISABLE_BUILTIN_INSTRUMENT", "0") != "1":
        asyncio.create_task(instrument_api_client.start_push_loop(use_http=False))
    asyncio.create_task(periodic_ws_broadcast_loop())


def run_server(host: str = "0.0.0.0", port: int = 8000):
    print(f"Starting Multi-Chamber Web UI & API Server: http://localhost:{port}")
    print(f"  - Web UI Dashboard         : http://localhost:{port}/")
    print(f"  - Swagger API Docs         : http://localhost:{port}/docs")
    print(f"  - Instrument Push Endpoint : POST http://localhost:{port}/api/telemetry")
    print(f"  - Web UI Data Endpoint     : GET  http://localhost:{port}/api/telemetry")
    uvicorn.run("web_gui.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
