@echo off
chcp 65001 >nul
title Badminton Studio · 羽毛球 AI 视频剪辑大师 v1.8.0 (Windows 桌面版)
cd /d "%~dp0"

echo ============================================================
echo   🏸 Badminton Studio · 羽毛球 AI 视频剪辑大师 v1.8.0
echo   正在启动本地高速引擎并打开独立可视化桌面窗口...
echo ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.9+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

python -c "import numpy, cv2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 正在首次自动安装轻量级视频分析依赖库 (numpy, opencv-python)...
    python -m pip install numpy opencv-python -i https://pypi.tuna.tsinghua.edu.cn/simple
)

REM 自动在 Windows 桌面创建带「猫猫打羽毛球」专属图标的桌面快捷方式
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\羽毛球AI剪辑大师.lnk'); $s.TargetPath = '%~f0'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0assets\app_icon.ico'; $s.WindowStyle = 7; $s.Save()" >nul 2>nul

start "" pythonw "%~dp0scripts\codex_server.py"
if %errorlevel% neq 0 (
    python "%~dp0scripts\codex_server.py"
)
