@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)
python -m pip install --quiet tkinterdnd2
python converter.py
if errorlevel 1 pause