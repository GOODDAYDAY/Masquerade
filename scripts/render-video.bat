@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - Video Renderer (Remotion)
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

REM Render video via Remotion
node scripts/render-video.mjs %SCRIPT%
if %errorlevel% neq 0 (
    echo.
    echo Render FAILED.
    pause
    exit /b 1
)

echo.
pause
