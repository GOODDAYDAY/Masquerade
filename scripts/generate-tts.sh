#!/bin/bash
set -e
# Generate TTS audio from a game script JSON
# Usage: generate-tts.sh <path_to_script.json>
# Prerequisite: pip install edge-tts

cd "$(dirname "$0")/.."

if [ -z "$1" ]; then
    echo "Usage: generate-tts.sh <path_to_script.json>"
    echo "Example: generate-tts.sh output/scripts/game_spy_20260314_155258.json"
    exit 1
fi

echo "Generating TTS audio..."
python -m backend.tts.generate "$1"

echo ""
echo "TTS generation finished."
