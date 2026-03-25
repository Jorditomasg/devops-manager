#!/bin/bash
cd "$(dirname "$0")/.."
echo "==================================================="
echo "DevOps Manager - Compilacion con Nuitka"
echo "==================================================="
echo ""

if [ ! -f ".venv/bin/activate" ]; then
    echo "Error: El entorno virtual no existe. Ejecuta install.sh primero."
    exit 1
fi

echo "[1/2] Activando el entorno virtual e instalando dependencias de compilacion..."
source .venv/bin/activate
pip install -r requirements-build.txt
if [ $? -ne 0 ]; then
    echo "Error durante la instalacion de dependencias."
    exit $?
fi

echo "[2/2] Compilando la aplicacion (esto puede tardar varios minutos)..."
python -m nuitka --standalone --follow-imports --include-package=customtkinter,darkdetect,pystray,PIL,git,yaml --include-package-data=customtkinter --include-data-dir=config=config --include-data-dir=assets=assets --output-dir=dist --output-filename=devops-manager --assume-yes-for-downloads main.py

if [ $? -ne 0 ]; then
    echo "Error durante la compilacion."
    exit $?
fi

echo ""
echo "Compilacion completada con exito en dist/main.dist/devops-manager"
echo "Puedes ejecutarla usando './run_compiled.sh <ruta_del_workspace>'"
echo ""
