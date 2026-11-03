# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec for 羽毛球AI剪辑大师 (Codex Studio Windows 64-bit Standalone Edition v1.8.0)
Build command on Windows:
    pyinstaller --noconfirm --clean BadmintonAICutter_Win64.spec
"""

import os

block_cipher = None
root_dir = os.path.abspath(".")
scripts_dir = os.path.join(root_dir, "scripts")

datas = [
    (os.path.join(scripts_dir, "ui", "index.html"), "ui"),
]
if os.path.exists(os.path.join(root_dir, "bin", "ffmpeg.exe")):
    datas.append((os.path.join(root_dir, "bin", "ffmpeg.exe"), "bin"))

a = Analysis(
    [os.path.join(scripts_dir, "codex_server.py")],
    pathex=[scripts_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "badminton_cutter",
        "match_segmenter",
        "modes_handler",
        "gui_engine",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "torch", "tensorflow"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="羽毛球AI剪辑大师",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="羽毛球AI剪辑大师",
)
