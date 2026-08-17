@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   REELS AI FACTORY
echo ============================================================
echo   14 video uretir, sonra YouTube + TikTok + Instagram icin
echo   planlar (19:30 ve 22:00, Europe/Istanbul), bitince
echo   Telegram'a mesaj atar.
echo.
echo   Yarim kalan hafta varsa KALDIGI YERDEN devam eder.
echo   Tamamlanmis isi asla tekrarlamaz.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo HATA: .venv\Scripts\python.exe bulunamadi.
    echo Once INSTALL_FIRST_TIME.bat calistirin.
    pause
    exit /b 1
)

REM Parametresiz calisir: yarim kalan batch varsa onu surdurur,
REM hepsi bittiyse yeni haftayi acar.
set ARGS=--live
if "%1"=="--dry-run" set ARGS=--dry-run

.venv\Scripts\python.exe -m automation.simple_weekly_pipeline %ARGS%
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [TAMAM] Tum fazlar tamamlandi.
) else (
    echo [DURDU] Yukaridaki ozete bakin. Duzeltip bu dosyayi tekrar calistirin.
)

pause
exit /b %EXIT_CODE%
