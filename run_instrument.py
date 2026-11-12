#!/usr/bin/env python3
"""
Chamber Instrument API Service Entry Point (儀器端獨立 API 與資料傳送程序)
負責模擬/讀取機台感測器數據，並透過 HTTP POST 傳送到 Web UI 的 API 接口 (/api/telemetry)。
同時也在本地 Port 8001 提供儀器端自身的 REST API (/instrument/...)。
"""

import argparse
import os
import uvicorn
from chamber.instrument_api import create_instrument_api_app


def main():
    parser = argparse.ArgumentParser(description="Chamber Instrument API Transmitter & Service")
    parser.add_argument(
        "--web-ui-url",
        default=os.environ.get("WEB_UI_URL", "http://127.0.0.1:8000"),
        help="Target Web UI API base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("INSTRUMENT_PORT", 8001)),
        help="Port for the Instrument API server (default: 8001)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="Telemetry push interval in seconds (default: 0.25)",
    )
    args = parser.parse_args()

    print("========================================================")
    print("  ⚡ Chamber Instrument API Service (儀器端 API 傳送器)")
    print("========================================================")
    print(f"  - 儀器端 API 服務位址 : http://localhost:{args.port}/instrument/status")
    print(f"  - 儀器端 Swagger 文件 : http://localhost:{args.port}/docs")
    print(f"  - 目標 Web UI API 接口: POST {args.web_ui_url}/api/telemetry")
    print("========================================================")

    app = create_instrument_api_app(
        web_ui_api_url=args.web_ui_url,
        push_interval_sec=args.interval,
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, reload=False)


if __name__ == "__main__":
    main()
