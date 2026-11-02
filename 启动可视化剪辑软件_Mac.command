#!/bin/bash
export TK_SILENCE_DEPRECATION=1
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$DIR/scripts/badminton_gui.py" ]; then
    DIR="/Users/harry/.gemini/config/skills/badminton-video-cutter"
fi
python3 "$DIR/scripts/badminton_gui.py"
