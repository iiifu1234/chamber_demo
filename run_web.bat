@echo off
chcp 65001 >nul
echo 正在啟動 Chamber 遠端網頁監控中心 (Web GUI)...
echo 請在瀏覽器開啟: http://localhost:8000
echo 同區域網路設備 (手機/平板) 請開啟: http://[您的電腦IP]:8000
start http://localhost:8000
.\venv\Scripts\python.exe run_web.py
pause
