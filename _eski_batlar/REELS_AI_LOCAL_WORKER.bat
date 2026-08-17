@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - LOCAL WINDOWS WORKER
echo ============================================================
echo Mode     : LOCAL WORKER BRIDGE (Heartbeat + Command Poll)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.local_worker --run-once
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Local worker cycle completed.
) else (
    echo [FAILED] Local worker encountered an error.
)

pause
exit /b %EXIT_CODE%
