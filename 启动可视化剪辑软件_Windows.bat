@echo off
chcp 65001 >nul
title 羽毛球 AI 视频剪辑大师 v1.7.0 (Windows 可视化桌面版)
cd /d "%~dp0"

echo ============================================================
echo   🏸 羽毛球 AI 视频剪辑大师 v1.7.0 - 正在启动可视化界面...
echo ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.9+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

python -c "import numpy, PIL" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 正在首次自动安装轻量级依赖库 (numpy, Pillow)...
    python -m pip install numpy Pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
)

start "" pythonw "%~dp0scripts\badminton_gui.py"
if %errorlevel% neq 0 (
    python "%~dp0scripts\badminton_gui.py"
)
