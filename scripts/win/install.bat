@echo off
cd /d "%~dp0..\.."
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
echo Puedes iniciar la aplicacion ejecutando 'scripts\win\run.vbs' (sin terminal)
echo o 'scripts\win\run.bat' desde consola.
echo Para compilar con Nuitka, ejecuta 'scripts\win\compile.bat' (opcional).
echo.

:: Resolve clean absolute root path (no trailing backslash)
pushd "%~dp0..\.."
set "ROOT=%CD%"
popd

:: Create desktop shortcut
:: Pass paths via env vars so PowerShell reads them cleanly — no CMD quoting issues.
:: TargetPath = wscript.exe (reliable); VBS passed as quoted argument.
echo Creando acceso directo en el escritorio...
set "DM_VBS=%ROOT%\scripts\win\run.vbs"
set "DM_ICON=%ROOT%\assets\icons\icon_red.ico"
set "DM_ROOT=%ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell;$s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\DevOps Manager.lnk');$s.TargetPath=($env:SystemRoot+'\System32\wscript.exe');$s.Arguments=([char]34+$env:DM_VBS+[char]34);$s.IconLocation=($env:DM_ICON+',0');$s.Description='DevOps Manager';$s.WorkingDirectory=$env:DM_ROOT;$s.Save()" >nul 2>&1

if %errorlevel% equ 0 (
    echo Acceso directo creado en el escritorio.
) else (
    echo No se pudo crear el acceso directo ^(puedes crearlo manualmente^).
)
echo.
pause
