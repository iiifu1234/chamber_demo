@echo off
chcp 65001 >nul
echo 正在啟動 Chamber 儀器端 API 傳送服務 (Instrument API -> Web UI API)...
echo 目標 Web UI API: http://127.0.0.1:8000/api/telemetry
echo 儀器端 API 狀態: http://localhost:8001/instrument/status
.\venv\Scripts\python.exe run_instrument.py
pause
