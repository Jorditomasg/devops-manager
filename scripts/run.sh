#!/bin/bash
cd "$(dirname "$0")/.."

echo "Iniciando DevOps Manager..."
if [ ! -f ".venv/bin/activate" ]; then
    echo "El entorno virtual no existe. Por favor, ejecuta './install.sh' primero."
    exit 1
fi

source .venv/bin/activate
python3 main.py
