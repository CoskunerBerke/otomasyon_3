@echo off
setlocal

echo ===================================================
echo     REELS AI FACTORY - YOUTUBE OAUTH GIRISI
echo ===================================================
echo.

cd /d "%~dp0"

:: 1. Python Interpreter Resolution
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 2. Python Diagnostics
echo Python Diagnostik:
"%PYTHON_EXE%" -c "import sys; print('Python executable:', sys.executable); print('Python version:   ', sys.version.split()[0])"
if %errorlevel% neq 0 (
    echo [HATA] Python calistirilamadi!
    pause
    exit /b 1
)
echo.

:: 3. Preflight Dependency Check
"%PYTHON_EXE%" -c "import googleapiclient, google_auth_oauthlib, google.auth" >nul 2>&1
if %errorlevel% neq 0 (
    echo ===================================================
    echo [YOUTUBE DEPENDENCY ERROR]
    echo Required Google OAuth libraries are missing.
    echo.
    echo Lutfen once su komutu calistirin:
    echo "%PYTHON_EXE%" -m pip install -r requirements.txt
    echo ===================================================
    pause
    exit /b 1
)

:: 4. Client Secret Check
if not exist "%~dp0secrets\youtube\client_secret.json" (
    echo ===================================================
    echo [UYARI] secrets\youtube\client_secret.json bulunamadi!
    echo Lutfen Google Cloud Console'dan indirdiginiz OAuth istemci dosyasini
    echo '%~dp0secrets\youtube\client_secret.json'
    echo konumuna kopyalayin ve bu komutu tekrar calistirin.
    echo ===================================================
    pause
    exit /b 1
)

:: 5. Launch OAuth Flow
"%PYTHON_EXE%" automation\publish.py --youtube-auth

echo.
pause
