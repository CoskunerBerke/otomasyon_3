@echo off
setlocal

echo ============================================================
echo REELS AI FACTORY - INSTAGRAM SINGLE REEL LIVE TEST
echo ============================================================
echo Platform : Instagram
echo Account  : @builddverse
echo Reel     : REEL-2026-0010
echo Mode     : LIVE UPLOAD + LIVE PUBLISH
echo ============================================================
echo WARNING:
echo This will publish one real Reel to @builddverse.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.publishing.instagram_live_test
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Instagram live publish test completed successfully.
) else (
    echo [FAILED] Instagram live publish test failed. Check log above.
)

pause
exit /b %EXIT_CODE%
