@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - Game Recorder
echo ========================================
echo.

if "%1"=="" (
    echo Available scripts:
    echo.
    dir /b output\scripts\game_*.json 2>nul
    echo.
    set /p SCRIPT="Enter script filename: "
) else (
    set SCRIPT=%1
)

if "%SCRIPT%"=="" (
    echo No script selected.
    pause
    exit /b 1
)

if not exist "output\scripts\%SCRIPT%" (
    echo Script not found: output\scripts\%SCRIPT%
    pause
    exit /b 1
)

REM Install playwright if needed
python -c "import playwright" 2>nul
if %errorlevel% neq 0 (
    echo Installing playwright...
    pip install playwright
    python -m playwright install chromium
)

REM Record (handles frontend start/stop internally)
python scripts/record.py %SCRIPT%

echo.
pause
