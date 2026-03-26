#!/bin/bash
cd "$(dirname "$0")/.."

echo "Iniciando DevOps Manager..."
if [ ! -d ".venv" ]; then
    echo "El entorno virtual no existe. Por favor, ejecuta './install.sh' primero."
    exit 1
fi

uv run python main.py
