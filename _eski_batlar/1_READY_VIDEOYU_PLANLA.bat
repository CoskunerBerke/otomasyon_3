@echo off
setlocal

echo ===================================================
echo   REELS AI FACTORY - 1 READY VIDEO YAYINLAMA / PLANLAMA
echo ===================================================
echo.

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" automation\publish.py --count 1

echo.
pause
