@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - 14 VIDEO HAFTALIK PLANLAMA (7 GUN)
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Hedef: 14 READY Reel - 7 Gun boyunca gunde 2 slot (19:30, 22:00)
echo [INFO] YouTube Studio (@BuiIdVerse) + TikTok Studio (@kitchenverse360)
echo.

"%PYTHON_EXE%" "%~dp0automation\publish.py" --count 14

echo.
pause
