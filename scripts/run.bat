@echo off
chcp 65001 >nul
REM Run a complete game using default config
REM Prerequisite: pip install -e ".[dev]" and set API key in .env

echo Starting Masquerade game...
python -m backend.main %*
