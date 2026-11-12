"""
Multi-Chamber Web GUI Server (FastAPI + WebSocket)
Serves real-time bilingual/English dashboard and static image assets.
"""

import os
import json
import asyncio
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from commands.controller import ChamberController

app = FastAPI(title="Multi-Chamber Remote Web Monitor")

# Mount Static directory for Chamber images and custom assets
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
TEMPLATE_PATH = os.path.join(CURRENT_DIR, "templates", "index.html")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

controller = ChamberController()
active_websockets: Set[WebSocket] = set()


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            action = cmd.get("action")
            cid = cmd.get("chamber_id", "chamber-1")

            if action == "power_toggle":
                controller.power(cmd.get("value", True), chamber_id=cid)
            elif action == "run_toggle":
                t = controller.get_telemetry(chamber_id=cid)
                controller.run(t.state != 2, chamber_id=cid)
            elif action == "door_toggle":
                controller.toggle_door(chamber_id=cid)
            elif action == "alarm_toggle":
                t = controller.get_telemetry(chamber_id=cid)
                controller.alarm(t.state != 3, chamber_id=cid)
            elif action == "set_sv":
                temp = float(cmd["temp"]) if "temp" in cmd else None
                humi = float(cmd["humi"]) if "humi" in cmd else None
                controller.set_target(temp=temp, humi=humi, chamber_id=cid)
            elif action == "set_speed":
                controller.set_speed(float(cmd.get("value", 1.0)), chamber_id=cid)

    except WebSocketDisconnect:
        active_websockets.discard(websocket)
    except Exception:
        active_websockets.discard(websocket)


async def broadcast_loop():
    """Periodic telemetry broadcast to all connected web clients"""
    while True:
        await asyncio.sleep(0.15)
        if active_websockets:
            all_telemetry = controller.get_all_telemetry()
            
            data_map = {}
            for cid, t in all_telemetry.items():
                data_map[cid] = {
                    "time": t.timestamp,
                    "temp_pv": t.temp_pv,
                    "temp_sv": t.temp_sv,
                    "humi_pv": t.humi_pv,
                    "humi_sv": t.humi_sv,
                    "state": int(t.state),
                    "state_text": t.state_text,
                    "state_color": t.state_color,
                    "heater": t.heater,
                    "cooler": t.cooler,
                    "humidifier": t.humidifier,
                    "door_open": t.door_open,
                    "uptime": t.uptime_str,
                    "sim_speed": t.sim_speed,
                }

            payload = json.dumps({
                "type": "telemetry_multi",
                "chambers": data_map
            })

            stale = []
            for ws in active_websockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                active_websockets.discard(ws)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_loop())


def run_server(host: str = "0.0.0.0", port: int = 8000):
    print(f"Starting Multi-Chamber Web Server: http://localhost:{port}")
    uvicorn.run("web_gui.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
