@echo off
setlocal

echo ===================================================
echo     REELS AI FACTORY - INSTAGRAM CHROME GIRISI
echo ===================================================
echo.
echo Bu komut Instagram icin ozel Chrome profilini (port 9225) acar
echo ve haftalik calistirmanin planlama yapip yapamayacagini kontrol eder.
echo.
echo Giris yapilmamissa: acilan pencerede giris yapin, pencereyi ACIK BIRAKIN
echo ve bu dosyayi tekrar calistirin.
echo.
echo Hicbir sey paylasilmaz, planlanmaz veya yuklenmez - sadece kontrol.
echo.

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m automation.publishing.instagram_web_login

echo.
pause
