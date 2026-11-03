#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$DIR/scripts/codex_server.py" ]; then
    DIR="/Users/harry/.gemini/config/skills/badminton-video-cutter"
fi
python3 "$DIR/scripts/codex_server.py"
