@echo off
chcp 65001 >nul
title Chamber 外網展示分享工具 (Public Demo Share)
echo ========================================================
echo   ⚡ Chamber 遠端監控 - 外網即時分享 Demo 模式
echo ========================================================
echo.
echo 正在檢查本地 Chamber 網頁伺服器 (Port 8000)...

netstat -ano | findstr :8000 >nul
if %errorlevel% neq 0 (
    echo [提示] 尚未啟動本地伺服器，正在為您在背景啟動...
    start /b .\venv\Scripts\python.exe run_web.py >nul 2>&1
    timeout /t 3 /nobreak >nul
)

echo [OK] 本地伺服器就緒！
echo.
echo 正在向 Cloudflare 申請安全加密外網網址 (HTTPS)...
echo.
echo ========================================================
echo   請在下方尋找類似：
echo   👉 https://xxxxxx.trycloudflare.com 👈 的網址
echo   複製該網址傳給其他人，任何人用手機或電腦打開就能看到！
echo   (按 Ctrl+C 可停止外網連線)
echo ========================================================
echo.
.\cloudflared.exe tunnel --url http://localhost:8000
pause
