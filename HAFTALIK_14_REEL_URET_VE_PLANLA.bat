@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - HAFTALIK 14 REEL URET VE PLANLA
echo ============================================================
echo Target   : 14 Reels (7 Days x 2 Slots: 19:30 ^& 22:00)
echo Start    : the day after the last video already scheduled
echo Mode     : narrative_ambient_story (real history + ambient audio)
echo Upload   : YouTube + TikTok + Instagram (all three scheduled)
echo Timezone : Europe/Istanbul
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

rem Default is the narrated real-history mode with Flow's ambient audio.
rem   --dry-run  : no Flow, no uploads (mock provider end-to-end)
rem   --sessiz   : the original silent step-by-step construction Reels
rem   --ig-cloud : hand Instagram to the Railway worker instead of scheduling it
rem                on instagram.com (never both - that would post each Reel twice)
set MODE=narrative_ambient_story
set IGMODE=web
set RUNARG=--live

:parse
if "%~1"=="" goto run
if /i "%~1"=="--dry-run" set RUNARG=--dry-run
if /i "%~1"=="--sessiz"  set MODE=silent_global_step_by_step
if /i "%~1"=="--silent"  set MODE=silent_global_step_by_step
if /i "%~1"=="--ig-cloud" set IGMODE=cloud
shift
goto parse

:run
echo Running Simple Weekly Pipeline (%RUNARG%, %MODE%, instagram=%IGMODE%)...
echo.
.venv\Scripts\python.exe -m automation.simple_weekly_pipeline %RUNARG% --content-mode %MODE% --instagram-delivery %IGMODE%
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Weekly pipeline execution completed successfully.
) else (
    echo [FAILED] Weekly pipeline stopped - see terminal output above for the phase and Reel that needs attention.
    echo          Re-running this same file resumes from where it stopped; nothing is regenerated.
)

pause
exit /b %EXIT_CODE%
