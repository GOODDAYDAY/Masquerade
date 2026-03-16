@echo off
chcp 65001 >/dev/null 2>/dev/null
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - Run Tests
echo ========================================
echo.

cd frontend
call npx vitest run
if %errorlevel% neq 0 (
    echo.
    echo Tests FAILED.
    exit /b 1
)

echo.
echo ========================================
echo   Tests: ALL PASSED
echo ========================================
