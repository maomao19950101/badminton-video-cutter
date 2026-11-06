@echo off
chcp 65001 >nul
title 羽毛球比赛剪辑工作室 · Badminton Studio Pro (Windows 桌面版)
cd /d "%~dp0"

echo ============================================================
echo   🏸 羽毛球比赛剪辑工作室 · Badminton Studio Pro
echo   正在启动本地高速引擎并打开专业非编剪辑工作台...
echo ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.10+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

python -c "import numpy, cv2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 正在首次自动安装轻量级视频分析依赖库 (numpy, opencv-python)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

REM 自动在 Windows 桌面创建带专属图标的桌面快捷方式
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\羽毛球比赛剪辑工作室.lnk'); $s.TargetPath = '%~f0'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0assets\app_icon.ico'; $s.WindowStyle = 7; $s.Save()" >nul 2>nul

start "" pythonw "%~dp0scripts\codex_server.py"
if %errorlevel% neq 0 (
    python "%~dp0scripts\codex_server.py"
)
