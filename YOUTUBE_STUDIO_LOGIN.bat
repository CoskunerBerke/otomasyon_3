@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul

echo ===================================================
echo   REELS AI FACTORY - YOUTUBE STUDIO LOGIN (PORT 9224)
echo ===================================================
echo.

:: Detect Python interpreter
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [DEBUG] Python Executable: %PYTHON_EXE%
echo [INFO] Chrome aciliyor: https://studio.youtube.com/
echo [INFO] Port: 9224  Profil: %%LOCALAPPDATA%%\ReelsAIFactory\youtube-studio-profile
echo [INFO] Hedef Kanal: @BuiIdVerse
echo.

"%PYTHON_EXE%" "%~dp0automation\publish.py" --youtube-studio-login

echo.
pause
