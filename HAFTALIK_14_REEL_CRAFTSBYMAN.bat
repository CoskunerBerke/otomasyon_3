@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - CRAFTS BY MAN (IKINCI KANAL)
echo ============================================================
echo Target   : 14 Reels (7 Days x 2 Slots: 19:30 ^& 22:00)
echo Start    : the day after this brand's last scheduled video
echo Mode     : hidden_build_story (buried object + recurring craftsman)
echo Upload   : YouTube + TikTok  (Instagram su an KAPALI)
echo Timezone : Europe/Istanbul
echo ============================================================
echo.
echo DIKKAT: Bu dosya IKINCI kanal icindir. Ilk seri
echo         HAFTALIK_14_REEL_URET_VE_PLANLA.bat ile calisir ve
echo         bu calistirmadan hic etkilenmez.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

rem   --dry-run          : no Flow, no uploads (mock provider end-to-end)
rem   --start-date YYYY-MM-DD : force the first day of the week
set RUNARG=--live
set EXTRA=

:parse
if "%~1"=="" goto run
if /i "%~1"=="--dry-run" set RUNARG=--dry-run
if /i "%~1"=="--start-date" (
    set EXTRA=--start-date %~2
    shift
)
shift
goto parse

:run
echo Running Crafts By Man pipeline (%RUNARG% %EXTRA%)...
echo.
.venv\Scripts\python.exe -m automation.simple_weekly_pipeline %RUNARG% --brand craftsbyman %EXTRA%
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Crafts By Man weekly pipeline completed successfully.
) else (
    echo [FAILED] Pipeline stopped - see terminal output above.
    echo          Re-running this same file resumes from where it stopped.
    echo          BRAND_NOT_CONFIGURED gorursen: automation\brands.py icinde
    echo          CRAFTSBYMAN hesap bilgilerini doldurman gerekiyor.
)

pause
exit /b %EXIT_CODE%
