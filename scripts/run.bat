@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - AI Board Game Arena
echo ========================================
echo.

python -m backend.main --list
echo.

set /p GAME="Select game type: "

if "%GAME%"=="" (
    echo No game selected, exiting.
    pause
    exit /b 1
)

echo.
echo Starting game: %GAME%
echo ========================================
echo.

python -m backend.main %GAME%

echo.
echo ========================================
echo Game finished.
echo ========================================
pause
