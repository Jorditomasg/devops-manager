@echo off
cd /d "%~dp0..\.."

start "" "dist\main.dist\devops-manager.exe" %*
