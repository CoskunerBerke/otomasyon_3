@echo off
setlocal

echo ============================================================
echo BUILDVERSE - KANAL GIRISLERI
echo ============================================================
echo Bu komut BUILDVERSE kanalinin tarayicilarini acar:
echo   YouTube   port 9224
echo   TikTok    port 9223
echo   Instagram port 9225
echo.
echo Her markanin kendi Chrome profili ve portu vardir; bunlar
echo birbirini etkilemez.
echo.
echo Acilan pencerelerde YALNIZCA BUILDVERSE hesaplarina giris
echo yapin. Pencereleri ACIK BIRAKIN.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.publishing.brand_login --brand buildverse
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] Tarayicilar acildi. Giris yaptiktan sonra haftalik calistirmayi baslatabilirsiniz.
) else (
    echo [FAILED] Durdu - yukaridaki ciktiya bak.
    echo          Tarayici acilamadi.
)

pause
exit /b %EXIT_CODE%
