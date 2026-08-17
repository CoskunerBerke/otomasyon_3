@echo off
setlocal

echo ==============================================================================
echo REELS AI FACTORY - INSTAGRAM API PREFLIGHT
echo ==============================================================================

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.publishing.instagram_preflight
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [PREFLIGHT SUCCESS] Instagram API preflight passed.
) else (
    echo [PREFLIGHT NOTICE] Meta setup is required. See above instructions.
)

pause
exit /b %EXIT_CODE%
