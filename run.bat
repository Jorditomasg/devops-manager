@echo off
echo Iniciando DevOps Manager...
if not exist ".venv\Scripts\activate.bat" (
    echo El entorno virtual no existe. Por favor, ejecuta 'install.bat' primero.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py
pause
