@echo off
echo ===================================================
echo DevOps Manager - Instalacion del Entorno Virtual
echo ===================================================
echo.

echo [1/3] Creando el entorno virtual (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo Error al crear el entorno virtual. Asegurate de tener Python instalado y en el PATH.
    pause
    exit /b %errorlevel%
)

echo [2/3] Activando el entorno virtual e instalando dependencias (requirements.txt)...
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error durante la instalacion de dependencias.
    pause
    exit /b %errorlevel%
)

echo [3/3] Instalacion completada exitosamente.
echo.
echo Puedes iniciar la aplicacion ejecutando 'run.bat'
echo.
pause
