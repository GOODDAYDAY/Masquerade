@echo off
chcp 65001 >/dev/null 2>/dev/null
cd /d "%~dp0\.."

echo ========================================
echo   Masquerade - Build Check
echo ========================================
echo.

echo [1/2] TypeScript type check...
cd frontend
call npx tsc --noEmit
if %errorlevel% neq 0 (
    echo.
    echo TypeScript check FAILED.
    pause
    exit /b 1
)
echo TypeScript: OK

echo.
echo [2/2] Vite build...
call npx vite build
if %errorlevel% neq 0 (
    echo.
    echo Vite build FAILED.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build: ALL PASSED
echo ========================================
