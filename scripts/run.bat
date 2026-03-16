@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - AI Board Game Arena
echo   Play + Record + Export MP4
echo ========================================
echo.

python -m backend.main --list
echo.

set /p GAME="Select game type: "
if "%GAME%"=="" (
    echo No game selected.
    pause
    exit /b 1
)

echo.

REM Run the game
python -m backend.main %GAME%

REM Find the latest script file
for /f "delims=" %%f in ('dir /b /o-d output\scripts\game_%GAME%_*.json 2^>nul') do (
    set SCRIPT_FILE=%%f
    goto :found
)
echo Could not find script file.
pause
exit /b 1

:found
echo.
echo Script: %SCRIPT_FILE%

REM Install playwright if needed
python -c "import playwright" 2>nul
if %errorlevel% neq 0 (
    echo Installing playwright...
    pip install playwright
    python -m playwright install chromium
)

REM Record (headless, no browser window, auto audio merge)
echo.
python scripts/record.py %SCRIPT_FILE%

echo.
echo ========================================
echo   All Done!
echo ========================================
pause
