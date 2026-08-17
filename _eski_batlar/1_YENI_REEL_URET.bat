@echo off
chcp 65001 >nul
cd /d "%~dp0"
title REELS AI FACTORY - 1 REEL URETIMI

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0automation\run.py" --count 1 --allow-real-generation
) else (
    python "%~dp0automation\run.py" --count 1 --allow-real-generation
)

echo.
pause
