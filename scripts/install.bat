@echo off
cd /d "%~dp0.."
echo ===================================================
echo DevOps Manager - Instalacion del Entorno Virtual
echo ===================================================
echo.

echo [1/2] Verificando uv...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo uv no encontrado. Instalando uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo Error al instalar uv. Visita https://docs.astral.sh/uv/ para instalarlo manualmente.
        pause
        exit /b 1
    )
    :: Agregar uv al PATH de esta sesion
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    echo uv instalado correctamente.
    echo.
)

echo [2/2] Instalando dependencias con uv (descargara Python si es necesario)...
uv sync
if %errorlevel% neq 0 (
    echo Error durante la instalacion de dependencias.
    pause
    exit /b %errorlevel%
)

echo.
echo Instalacion completada exitosamente.
echo Puedes iniciar la aplicacion ejecutando 'run.bat'
echo Para compilar con Nuitka, ejecuta 'compile.bat' (opcional).
echo.
pause
