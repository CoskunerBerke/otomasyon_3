@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - 1 REEL LIVE SCHEDULE TEST
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Bu test yalnizca 1 READY Reel secer ve YouTube Studio + TikTok Studio uzerinde canli test eder.
echo [INFO] Test basarili olduktan sonra 14_VIDEOYU_PLANLA.bat calistirilabilir.
echo.

"%PYTHON_EXE%" "%~dp0automation\publish.py" --count 1 --single-live-test --enable-live-publish

echo.
pause
