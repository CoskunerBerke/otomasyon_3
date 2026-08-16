@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - HAFTALIK 14 REEL URET VE PLANLA
echo ============================================================
echo Target   : 14 V3 Reels (7 Days x 2 Slots: 19:30 & 22:00)
echo Timezone : Europe/Istanbul
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

set ARGS=--live
if "%1"=="--dry-run" set ARGS=--dry-run

echo Running Weekly Orchestrator (%ARGS%)...
.venv\Scripts\python.exe -m automation.weekly_orchestrator %ARGS%
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Weekly pipeline execution completed successfully.
) else (
    echo [FAILED] Weekly orchestrator encountered an error.
)

pause
exit /b %EXIT_CODE%
