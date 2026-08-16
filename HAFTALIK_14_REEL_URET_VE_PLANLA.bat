@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - HAFTALIK 14 REEL URET VE PLANLA
echo ============================================================
echo Mode     : DRY RUN (SIMULATION)
echo Target   : 14 V3 Reels (7 Days x 2 Slots: 19:30 & 22:00)
echo Timezone : Europe/Istanbul
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.weekly_orchestrator --dry-run
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Weekly orchestrator plan generated successfully.
) else (
    echo [FAILED] Weekly orchestrator encountered an error.
)

pause
exit /b %EXIT_CODE%
