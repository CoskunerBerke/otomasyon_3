@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - 14 VIDEO URET VE PLANLA
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [ASAMA 1/2] 14 Yeni V3 Reel Uretimi Baslatiliyor...
echo.
"%PYTHON_EXE%" "%~dp0automation\run.py" --count 14
if errorlevel 1 (
    echo [HATA] Video uretimi sirasinda hata olustu. Planlama baslatilamadi.
    pause
    exit /b 1
)

echo.
echo [ASAMA 2/2] 14 Video Haftalik Planlama Baslatiliyor...
echo.
"%PYTHON_EXE%" "%~dp0automation\publish.py" --count 14

echo.
pause
