@echo off
chcp 65001 >nul
cd /d "%~dp0"
title REELS AI FACTORY - GOOGLE FLOW GIRIS
echo ========================================================
echo         GOOGLE FLOW - GOOGLE CHROME GİRİŞİ
echo ========================================================
echo Calisma Dizini: %CD%
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0automation\flow\chrome_launcher.py"
) else (
    python "%~dp0automation\flow\chrome_launcher.py"
)

echo.
pause
