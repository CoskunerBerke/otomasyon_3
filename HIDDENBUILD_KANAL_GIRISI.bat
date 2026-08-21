@echo off
setlocal

echo ===================================================
echo   CRAFTS BY MAN - KANAL GIRISLERI (IKINCI KANAL)
echo ===================================================
echo.
echo Bu komut IKINCI kanalin uc tarayicisini acar:
echo   YouTube   port 9234
echo   TikTok    port 9233
echo   Instagram port 9235
echo.
echo Bunlar ILK kanalin tarayicilarindan (9223/9224/9225)
echo tamamen ayridir ve birbirini etkilemez.
echo.
echo Acilan pencerelerde YALNIZCA craftsbyman hesaplarina
echo giris yapin. Pencereleri ACIK BIRAKIN.
echo.

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m automation.publishing.brand_login --brand hiddenbuild

echo.
pause
