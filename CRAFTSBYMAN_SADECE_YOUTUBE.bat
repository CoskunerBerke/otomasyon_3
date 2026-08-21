@echo off
setlocal

echo ============================================================
echo CRAFTS BY MAN - SADECE YOUTUBE (EKSIK REEL'LERI TAMAMLAR)
echo ============================================================
echo Hafta    : CBM-2026-W34 (22-28 Agustos)
echo Yapar    : Sadece YouTube'a eksik Reel'leri yukler
echo Yapmaz   : Uretim yok, TikTok yok, Instagram yok
echo.
echo Neden ayri bir dosya:
echo   Tek-faz calistirma 30 dk'lik "takildi" bekleme dongusune
echo   girmez. 2026-08-21'de 14 Reel'i 28 videoya ceviren sey o
echo   dongunun iki tur donmesiydi. Bu dosyada o risk yok.
echo.
echo Zaten planli olan Reel'lere dokunulmaz (SCHEDULED = atlanir).
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.simple_weekly_pipeline ^
    --live --brand craftsbyman --week-id CBM-2026-W34 --phase youtube
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] YouTube fazi tamamlandi.
) else (
    echo [FAILED] Durdu - yukaridaki ciktiya bak.
    echo          Ayni dosyayi tekrar calistirmak kaldigi yerden devam eder;
    echo          zaten yuklenmis Reel tekrar yuklenmez.
)

pause
exit /b %EXIT_CODE%
