@echo off
chcp 65001 >nul
REM Start the Game Theater dev server
REM Prerequisite: npm install in frontend/

cd /d "%~dp0\..\frontend"

echo Starting Masquerade Theater (dev server)...
echo Open http://localhost:5173 in your browser
echo.

call npx vite
