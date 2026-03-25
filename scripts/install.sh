#!/bin/bash
cd "$(dirname "$0")/.."

echo "==================================================="
echo "DevOps Manager - Instalacion del Entorno Virtual"
echo "==================================================="
echo ""

echo "[1/3] Creando el entorno virtual (.venv)..."
python3 -m venv .venv || { echo "Error al crear el entorno virtual. Asegurate de tener python3-venv instalado."; exit 1; }

echo "[2/3] Activando el entorno virtual e instalando dependencias (requirements.txt)..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || { echo "Error durante la instalacion de dependencias."; exit 1; }

echo "[3/3] Instalacion completada exitosamente."
echo ""
echo "Puedes iniciar la aplicacion ejecutando './run.sh'"
echo ""
