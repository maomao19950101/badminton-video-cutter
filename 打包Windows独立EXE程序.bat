@echo off
chcp 65001 >nul
title Codex Studio · 羽毛球 AI 视频剪辑大师 - Windows 独立 EXE 一键打包工具
cd /d "%~dp0"

echo ============================================================
echo   📦 正在打包【羽毛球AI剪辑大师.exe】独立 Windows 桌面程序...
echo ============================================================

python -m pip install pyinstaller numpy opencv-python -i https://pypi.tuna.tsinghua.edu.cn/simple

pyinstaller --noconfirm --clean --windowed ^
    --name "羽毛球AI剪辑大师" ^
    --icon "%~dp0assets\app_icon.ico" ^
    --paths "%~dp0scripts" ^
    --add-data "%~dp0scripts\ui\index.html;ui" ^
    --add-data "%~dp0assets;assets" ^
    --hidden-import "badminton_cutter" ^
    --hidden-import "match_segmenter" ^
    --hidden-import "modes_handler" ^
    --hidden-import "gui_engine" ^
    "%~dp0scripts\codex_server.py"

if exist "%~dp0bin\ffmpeg.exe" (
    mkdir "%~dp0dist\羽毛球AI剪辑大师\bin" 2>nul
    copy /Y "%~dp0bin\ffmpeg.exe" "%~dp0dist\羽毛球AI剪辑大师\bin\ffmpeg.exe" >nul
)

echo.
echo ============================================================
echo   ✅ 打包完成！
echo   独立程序路径: %~dp0dist\羽毛球AI剪辑大师\羽毛球AI剪辑大师.exe
echo ============================================================
pause
