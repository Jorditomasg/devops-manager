@echo off
if "%~1"=="" (
    echo Usa: run_compiled.bat ^<ruta_del_workspace^>
    exit /b 1
)

start "" "dist\main.dist\devops-manager.exe" "%~1"
