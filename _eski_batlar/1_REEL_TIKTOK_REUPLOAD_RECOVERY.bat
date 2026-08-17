@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - TIKTOK REUPLOAD RECOVERY
echo ===================================================
echo.
echo [SAFETY] YouTube'a BAGLANMAZ.
echo [SAFETY] Yalnizca REEL-2026-0010 final MP4 TikTok'a yuklenir.
echo [TARGET] 16.08.2026 19:30
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if not exist "%~dp0automation\recover_tiktok_reel_0010.py" (
    echo [HATA] automation\recover_tiktok_reel_0010.py bulunamadi.
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0automation\recover_tiktok_reel_0010.py"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [OK] TikTok recovery tamamlandi.
) else (
    echo [HATA] Recovery guvenli sekilde durdu. Exit code: %EXIT_CODE%
)

echo.
pause
exit /b %EXIT_CODE%
