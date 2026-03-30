@echo off
cd /d "%~dp0.."
echo ===================================================
echo DevOps Manager - Compilar + Generar Instalador
echo ===================================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo Error: El entorno virtual no existe. Ejecuta install.bat primero.
    pause
    exit /b 1
)

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo Error: Inno Setup no encontrado en %ISCC%
    echo Descargalo desde: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo [1/3] Activando el entorno virtual...
call .venv\Scripts\activate.bat

echo [2/3] Compilando la aplicacion con Nuitka...
python -m nuitka --standalone --follow-imports --enable-plugin=tk-inter --include-package=customtkinter,darkdetect,pystray,PIL,git,yaml --include-package-data=customtkinter --include-data-dir=config=config --include-data-dir=assets=assets --windows-console-mode=hide --windows-icon-from-ico=assets\icons\icon_red.ico --output-dir=dist --output-filename=devops-manager --assume-yes-for-downloads main.py
if %errorlevel% neq 0 (
    echo Error durante la compilacion.
    pause
    exit /b %errorlevel%
)

echo [3/3] Generando instalador con Inno Setup...
%ISCC% installer.iss
if %errorlevel% neq 0 (
    echo Error generando el instalador.
    pause
    exit /b %errorlevel%
)

echo.
echo ===================================================
echo Instalador generado en: dist\devops-manager-setup.exe
echo ===================================================
echo.
pause
