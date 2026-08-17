@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - 14 YENI V3 REEL URETIMI
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Hedef: 14 YENI V3 Reel (42 Flow Segment Generation, 30s Final MP4)
echo.

"%PYTHON_EXE%" "%~dp0automation\run.py" --count 14

echo.
pause
