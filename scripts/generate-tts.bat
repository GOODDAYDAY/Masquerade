@echo off
chcp 65001 >nul
REM Generate TTS audio from a game script JSON
REM Usage: generate-tts.bat <path_to_script.json>
REM Prerequisite: pip install edge-tts

cd /d "%~dp0\.."

if "%1"=="" (
    echo Usage: generate-tts.bat ^<path_to_script.json^>
    echo Example: generate-tts.bat output\scripts\game_spy_20260314_155258.json
    exit /b 1
)

REM Force Python to use UTF-8 for stdout/stderr on Windows
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Generating TTS audio...
python -m backend.tts.generate %1

echo.
echo TTS generation finished.
