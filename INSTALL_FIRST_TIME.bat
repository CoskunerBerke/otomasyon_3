@echo off
chcp 65001 >nul
cd /d "%~dp0"
title REELS AI FACTORY - ILK KURULUM
echo ========================================================
echo       REELS AI FACTORY - ILK KURULUM YONETICISI
echo ========================================================
echo Calisma Dizini: %CD%
echo.

:: 1. Python Kontrolu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi!
    echo Lutfen Python 3.10 veya daha yenisini kurun ve 'Add Python to PATH' kutusunu isaretleyin.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] Python bulundu.

:: 2. FFmpeg Kontrolu
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [UYARI] FFmpeg PATH icinde bulunamadi!
    echo Kalite kontrolu ve ses temizleme icin FFmpeg gereklidir.
    echo Lutfen FFmpeg'i kurup sistem PATH'ine ekleyin.
    echo (Ornek: winget install Gyan.FFmpeg)
    echo.
) else (
    echo [2/5] FFmpeg bulundu.
)

:: 3. Virtual Environment (venv) Kurulumu
echo [3/5] Sanal ortam (.venv) kontrol ediliyor...
if not exist "%~dp0.venv" (
    echo Sanal ortam olusturuluyor...
    python -m venv "%~dp0.venv"
)
call "%~dp0.venv\Scripts\activate.bat"

:: 4. Python Paketleri Kurulumu
echo [4/5] Gerekli Python kutuphaneleri kuruluyor...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo [HATA] Kutuphaneler kurulurken hata olustu.
    pause
    exit /b 1
)

:: 5. Playwright Chromium Tarayicisi Kurulumu
echo [5/5] Playwright Chromium tarayicisi kuruluyor...
"%~dp0.venv\Scripts\playwright.exe" install chromium
if %errorlevel% neq 0 (
    echo [HATA] Playwright tarayicisi kurulurken hata olustu.
    pause
    exit /b 1
)

:: 6. Config Dosyasi Kontrolu
if not exist "%~dp0config.local.json" (
    if exist "%~dp0config.example.json" (
        copy "%~dp0config.example.json" "%~dp0config.local.json" >nul
        echo config.local.json olusturuldu.
    )
)

echo.
echo ========================================================
echo               KURULUM BASARIYLA TAMAMLANDI!
echo ========================================================
echo Simdi sirasiyla:
echo 1. FLOW_LOGIN.bat ile Google Flow hesabiniza giris yapin.
echo 2. YOUTUBE_LOGIN.bat ile YouTube hesabinizi yetkilendirin.
echo 3. BUILDVERSE_GIRIS.bat ile TikTok Studio hesabiniza giris yapin.
echo 4. 1_YENI_REEL_URET.bat veya 3_YENI_REEL_URET.bat ile uretim yapin.
echo ========================================================
echo.
pause
