@echo off
chcp 65001 >nul
REM Run integration tests

cd /d "%~dp0\.."

echo Running tests...

echo === Spy Game Tests ===
python -m backend.tests.test_spy_game
if %errorlevel% neq 0 (
    echo Spy game tests FAILED.
    exit /b 1
)

echo === Blank Game Tests ===
python -m backend.tests.test_blank_game
if %errorlevel% neq 0 (
    echo Blank game tests FAILED.
    exit /b 1
)

echo === Script Pipeline Tests ===
python -m backend.tests.test_script_pipeline
if %errorlevel% neq 0 (
    echo Script pipeline tests FAILED.
    exit /b 1
)

echo === Werewolf AC Tests ===
python -m backend.tests.verify_ac
if %errorlevel% neq 0 (
    echo Werewolf AC tests FAILED.
    exit /b 1
)

echo All tests completed.
