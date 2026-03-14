@echo off
chcp 65001 >nul
REM Build the project — install backend + frontend dependencies
REM Prerequisite: Python 3.11+, Node.js 18+

cd /d "%~dp0\.."

echo === Backend ===
echo Installing Python dependencies...
pip install -e ".[dev,render]"

echo.
echo === Frontend ===
echo Installing npm dependencies...
cd frontend
call npm install
echo Building frontend...
call npx tsc -b
call npx vite build
cd ..

echo.
echo Build completed.
