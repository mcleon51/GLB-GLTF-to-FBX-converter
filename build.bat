@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set APP_NAME=3D Converter

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Установка зависимостей...
python -m pip install --quiet --upgrade pyinstaller tkinterdnd2
if errorlevel 1 (
    echo Не удалось установить зависимости.
    pause
    exit /b 1
)

REM tkinterdnd2 ищет свои .tcl через os.path.dirname(__file__), поэтому в bundle
REM структура папок должна повторять исходную: tkinterdnd2/tkdnd/^<платформа^>
for /f "delims=" %%i in ('python -c "import os,tkinterdnd2; p=os.path.join(os.path.dirname(tkinterdnd2.__file__),'tkdnd'); m=os.environ.get('PROCESSOR_ARCHITECTURE') or 'AMD64'; d='win-x64' if m=='AMD64' else ('win-x86' if m=='x86' else 'win-arm64'); print(os.path.join(p,d))"') do set TKDND_SRC=%%i

if not exist "%TKDND_SRC%" (
    echo Не найдена папка tkdnd: %TKDND_SRC%
    pause
    exit /b 1
)

for %%f in ("%TKDND_SRC%") do set TKDND_NAME=%%~nxf
echo       tkdnd: %TKDND_NAME%

echo [2/4] Очистка предыдущей сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] Сборка %APP_NAME%.exe...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --add-data "blender_convert.py;." ^
    --add-data "%TKDND_SRC%;tkinterdnd2/tkdnd/%TKDND_NAME%" ^
    --hidden-import tkinterdnd2 ^
    converter.py

if errorlevel 1 (
    echo Сборка не удалась.
    pause
    exit /b 1
)

echo [4/4] Готово: dist\%APP_NAME%.exe
pause
