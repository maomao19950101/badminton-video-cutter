#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
    exec uv run --python 3.12 --with-requirements requirements.txt python scripts/codex_server.py "$@"
fi
if ! python3 -c 'import cv2, numpy' 2>/dev/null; then
    printf '%s\n' '请使用安装了 Python 依赖的环境，或安装 uv 后重新启动。详见 README.md。' >&2
    exit 1
fi
exec python3 scripts/codex_server.py "$@"
