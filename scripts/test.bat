@echo off
chcp 65001 >nul
REM Run all tests
REM Prerequisite: pip install -e ".[dev]"

echo Running tests...
python -m pytest tests/ -v
echo Tests completed.
