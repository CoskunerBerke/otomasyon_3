@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - TIKTOK ONLY LIVE COMMIT
echo ===================================================
echo.
echo [SAFETY] YouTube bu komutta tamamen ATLANIR.
echo [SAFETY] Yeni video upload edilmez.
echo [TARGET] TikTok: @kitchenverse360
echo [TARGET] REEL-2026-0010 - 16.08.2026 19:30
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if not exist "%~dp0automation\commit_tiktok_only.py" (
    echo [HATA] automation\commit_tiktok_only.py bulunamadi.
    echo ZIP paketini proje kok klasorune klasor yapisini koruyarak cikartin.
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0automation\commit_tiktok_only.py" --scheduled-at "2026-08-16T19:30:00+03:00"

set "EXIT_CODE=%ERRORLEVEL%"
echo.

if "%EXIT_CODE%"=="0" (
    echo [OK] TikTok-only commit tamamlandi.
) else (
    echo [HATA] TikTok-only commit guvenli sekilde durdu. Exit code: %EXIT_CODE%
)

echo.
pause
exit /b %EXIT_CODE%
