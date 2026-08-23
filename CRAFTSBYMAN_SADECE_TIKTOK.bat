@echo off
setlocal

echo ============================================================
echo CRAFTS BY MAN - SADECE TIKTOK
echo ============================================================
echo Hafta    : CBM-2026-W34 (22-28 Agustos)
echo Yapar    : Sadece TikTok'a eksik Reel'leri yukler
echo Yapmaz   : Uretim yok, YouTube yok, Instagram yok
echo.
echo ONCE SUNU YAP:
echo   1) CRAFTSBYMAN_GIRIS.bat calistir
echo   2) Acilan TikTok penceresinde yukleme sayfasina bak ve
echo      cikan TUM tanitim/bilgilendirme kutularini kapat
echo   3) Sayfa temiz kalana kadar devam et, sonra bu dosyayi calistir
echo.
echo   Yeni hesapta o tanitim turu bir kere cikar ve bir daha
echo   asla cikmaz. Otomasyon onu gecmeye calisirsa 0001'de takilir
echo   (2026-08-21'de tam olarak bu oldu). Bir kez elle kapat, biter.
echo.
echo Tek-faz calistirma 30 dk'lik bekleme dongusune girmez.
echo Zaten planli olan Reel'lere dokunulmaz.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.simple_weekly_pipeline ^
    --live --brand craftsbyman --week-id CBM-2026-W34 --phase tiktok
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] TikTok fazi tamamlandi.
) else (
    echo [FAILED] Durdu - yukaridaki ciktiya bak.
    echo          Ayni dosyayi tekrar calistirmak kaldigi yerden devam eder;
    echo          zaten planlanmis Reel tekrar yuklenmez.
)

pause
exit /b %EXIT_CODE%
