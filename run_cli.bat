@echo off
chcp 65001 >nul
echo 正在啟動 Chamber 命令終端 (CLI)...
.\venv\Scripts\python.exe -m commands.cli
pause
