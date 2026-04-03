@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\pythonw.exe" (
    echo El entorno virtual no existe. Por favor, ejecuta 'install.bat' primero.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py
