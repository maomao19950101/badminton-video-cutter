@echo off
chcp 65001 >nul
title Codex Studio · 羽毛球 AI 视频剪辑大师 v1.8.0 (Windows 桌面版)
cd /d "%~dp0"

echo ============================================================
echo   🏸 Codex Studio · 羽毛球 AI 视频剪辑大师 v1.8.0
echo   正在启动本地高速引擎并打开独立可视化桌面窗口...
echo ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.9+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

python -c "import numpy" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 正在首次自动安装轻量级依赖库 (numpy)...
    python -m pip install numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
)

start "" pythonw "%~dp0scripts\codex_server.py"
if %errorlevel% neq 0 (
    python "%~dp0scripts\codex_server.py"
)
