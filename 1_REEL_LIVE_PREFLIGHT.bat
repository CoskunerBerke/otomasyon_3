@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - 1 REEL LIVE PREFLIGHT (PHASE 1)
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Bu komut yalnizca PREFLIGHT asamasidir.
echo [INFO] YouTube ve TikTok formlarini eksiksiz hazirlar, FAKAT final butonlara BASMAZ (0 Clicks).
echo [INFO] Formlari browser uzerinde kontrol ettikten sonra '1_REEL_LIVE_COMMIT.bat' calistiriniz.
echo.

"%PYTHON_EXE%" "%~dp0automation\publish.py" --count 1 --preflight --enable-live-publish

echo.
pause
