@echo off
setlocal

echo ============================================================
echo BUILDVERSE - SADECE YOUTUBE
echo ============================================================
echo Kanal    : BUILDVERSE
echo Yapar    : Sadece YOUTUBE'a eksik Reel'leri yukler
echo Yapmaz   : Uretim yok, diger platformlara dokunmaz
echo.
echo Tek-faz calistirma 30 dk'lik bekleme dongusune girmez.
echo Zaten planlanmis Reel'ler atlanir.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m automation.simple_weekly_pipeline ^
    --live --brand buildverse --phase youtube
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo [SUCCESS] YOUTUBE fazi tamamlandi.
) else (
    echo [FAILED] Durdu - yukaridaki ciktiya bak.
    echo          Ayni dosyayi tekrar calistirmak kaldigi yerden devam eder;
    echo          zaten planlanmis Reel tekrar yuklenmez.
)

pause
exit /b %EXIT_CODE%
