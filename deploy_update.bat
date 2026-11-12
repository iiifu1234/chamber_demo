@echo off
chcp 65001 >nul
title Chamber 雲端網頁一鍵更新部署工具
echo ========================================================
echo   🚀 Chamber 雲端更新發布工具 (GitHub + Render 自動同步)
echo ========================================================
echo.
echo 正在檢查本地檔案變更...
git status -s
echo.
set /p msg="請輸入本次更新說明 (直接按 Enter 預設為 Update): "
if "%msg%"=="" set msg=Update chamber monitor

echo.
echo [1/3] 正在打包所有變更...
git add .

echo [2/3] 正在建立版本紀錄...
git commit -m "%msg%"

echo [3/3] 正在推送至 GitHub (iiifu1234/chamber_demo)...
git push origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo   ✅ 更新已成功發布至 GitHub！
    echo   Render 雲端將在 30 ~ 60 秒內自動為您完成重新部署。
    echo   重新整理您的 Render 網址即可看到最新內容！
    echo ========================================================
) else (
    echo.
    echo ❌ 推送失敗，請確認網路連線或是否有權限。
)

echo.
pause
