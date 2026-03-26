@echo off
cd /d "%~dp0.."
echo ===================================================
echo DevOps Manager - Instalacion del Entorno Virtual
echo ===================================================
echo.

echo [1/2] Verificando uv...
set "UV_CMD=uv"
where uv >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        :: uv was installed but is not in PATH
        set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
        echo uv encontrado en %USERPROFILE%\.local\bin\uv.exe
    ) else (
        echo uv no encontrado. Intentando instalar uv via pip...
        python -m pip install uv
        if %errorlevel% neq 0 (
            echo Fallo instalacion via pip. Intentando con script de PowerShell...
            powershell -ExecutionPolicy ByPass -c "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://astral.sh/uv/install.ps1 | iex"
            if not exist "%USERPROFILE%\.local\bin\uv.exe" (
                echo Error al instalar uv. Visita https://docs.astral.sh/uv/ para instalarlo manualmente.
                pause
                exit /b 1
            )
            set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
        ) else (
            set "UV_CMD=python -m uv"
        )
        echo uv instalado correctamente.
        echo.
    )
)

echo [2/2] Instalando dependencias con uv (descargara Python si es necesario)...
%UV_CMD% sync
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
