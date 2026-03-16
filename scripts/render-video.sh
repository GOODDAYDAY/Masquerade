#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "========================================"
echo "  Masquerade - Video Renderer (Remotion)"
echo "========================================"
echo ""

SCRIPT="${1}"

if [ -z "$SCRIPT" ]; then
    echo "Available scripts:"
    echo ""
    ls -1 output/scripts/game_*.json 2>/dev/null | xargs -I{} basename {}
    echo ""
    read -p "Enter script filename: " SCRIPT
fi

if [ -z "$SCRIPT" ]; then
    echo "No script selected."
    exit 1
fi

if [ ! -f "output/scripts/$SCRIPT" ]; then
    echo "Script not found: output/scripts/$SCRIPT"
    exit 1
fi

# Render video via Remotion
node scripts/render-video.mjs "$SCRIPT"

echo ""
echo "Done!"
