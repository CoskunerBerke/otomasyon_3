@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - RAILWAY PRODUCTION PREFLIGHT
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.cloud.railway_production_preflight
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Railway production preflight passed.
) else (
    echo [ACTION REQUIRED] Please review configuration errors above.
)

pause
exit /b %EXIT_CODE%
