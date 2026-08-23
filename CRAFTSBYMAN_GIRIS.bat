@echo off
setlocal

echo ============================================================
echo CRAFTS BY MAN - KANAL GIRISLERI
echo ============================================================
echo Bu komut CRAFTS BY MAN kanalinin tarayicilarini acar:
echo   YouTube   port 9234
echo   TikTok    port 9233
echo.
echo   Instagram bu kanal icin KAPALI -- tarayicisi acilmaz.
echo   Acmak icin automationrands.py icinde platforms listesine ekleyin.
echo.
echo Her markanin kendi Chrome profili ve portu vardir; bunlar
echo birbirini etkilemez.
echo.
echo Acilan pencerelerde YALNIZCA CRAFTS BY MAN hesaplarina giris
echo yapin. Pencereleri ACIK BIRAKIN.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.publishing.brand_login --brand craftsbyman
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
