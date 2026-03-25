@echo off
echo ===================================================
echo DevOps Manager - Compilacion con Nuitka
echo ===================================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo Error: El entorno virtual no existe. Ejecuta install.bat primero.
    exit /b 1
)

echo [1/2] Activando el entorno virtual e instalando dependencias de compilacion...
call .venv\Scripts\activate.bat
pip install -r requirements-build.txt
if %errorlevel% neq 0 (
    echo Error durante la instalacion de dependencias.
    exit /b %errorlevel%
)

echo [2/2] Compilando la aplicacion (esto puede tardar varios minutos)...
python -m nuitka --standalone --follow-imports --include-package=customtkinter,darkdetect,pystray,PIL,git,yaml --include-package-data=customtkinter --include-data-dir=config=config --include-data-dir=assets=assets --windows-console-mode=hide --windows-icon-from-ico=assets\icons\icon_red.ico --output-dir=dist --output-filename=devops-manager --assume-yes-for-downloads main.py

if %errorlevel% neq 0 (
    echo Error durante la compilacion.
    exit /b %errorlevel%
)

echo.
echo Compilacion completada con exito en dist\main.dist\devops-manager.exe
echo Puedes ejecutarla usando 'run_compiled.bat ^<ruta_del_workspace^>'
echo.
