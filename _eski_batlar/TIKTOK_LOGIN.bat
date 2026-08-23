@echo off
setlocal

echo ===================================================
echo     REELS AI FACTORY - TIKTOK STUDIO CHROME GIRISI
echo ===================================================
echo.
echo Bu komut TikTok icin ozel Chrome profilini (port 9223) acar.
echo Acilan pencerede TikTok hesabiniza manuel olarak giris yapin.
echo.

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -c "import sys; print('Python executable:', sys.executable)"
echo.

"%PYTHON_EXE%" automation\publish.py --tiktok-login

echo.
pause
