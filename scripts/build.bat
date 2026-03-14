@echo off
chcp 65001 >nul
REM Build the project — install dependencies
REM Prerequisite: Python 3.11+, uv or pip

echo Installing dependencies...
pip install -e ".[dev]"
echo Build completed.
