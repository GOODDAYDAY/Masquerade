@echo off
chcp 65001 >nul
REM Run integration tests

cd /d "%~dp0\.."

echo Running tests...
python -m backend.tests.test_spy_game
if %errorlevel% neq 0 (
    echo Tests FAILED.
    exit /b 1
)
echo Tests completed.
