#!/bin/bash
cd "$(dirname "$0")/.."

echo "==================================================="
echo "DevOps Manager - Instalacion del Entorno Virtual"
echo "==================================================="
echo ""

echo "[1/2] Verificando uv..."
if ! command -v uv &>/dev/null; then
    echo "uv no encontrado. Instalando uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "uv instalado correctamente."
    echo ""
fi

echo "[2/2] Instalando dependencias con uv (descargara Python si es necesario)..."
uv sync || { echo "Error durante la instalacion de dependencias."; exit 1; }

echo ""
echo "Instalacion completada exitosamente."
echo "Puedes iniciar la aplicacion ejecutando './run.sh'"
echo ""
