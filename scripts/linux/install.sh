#!/bin/bash
cd "$(dirname "$0")/../.."

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
echo "Puedes iniciar la aplicacion ejecutando './scripts/linux/run.sh'"
echo ""

# Create a .desktop shortcut for Linux desktop environments
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/devops-manager.desktop"
ROOT_DIR="$(pwd)"
ICON_PATH="$ROOT_DIR/assets/icons/icon_red.ico"
RUN_SCRIPT="$ROOT_DIR/scripts/linux/run.sh"

DESKTOP_ENTRY="[Desktop Entry]
Version=1.0
Type=Application
Name=DevOps Manager
Comment=Manage and launch development services
Exec=$RUN_SCRIPT
Icon=$ICON_PATH
Terminal=false
Categories=Development;Utility;
StartupNotify=true"

# Install in app launcher
if [ -d "$DESKTOP_DIR" ]; then
    echo "$DESKTOP_ENTRY" > "$DESKTOP_FILE"
    echo "Acceso directo en launcher: $DESKTOP_FILE"
fi

# Install on Desktop (if it exists)
DESKTOP_PHYSICAL="$HOME/Desktop"
if [ ! -d "$DESKTOP_PHYSICAL" ]; then
    # Some DEs use localised name (e.g. Escritorio)
    DESKTOP_PHYSICAL="$(xdg-user-dir DESKTOP 2>/dev/null)"
fi
if [ -d "$DESKTOP_PHYSICAL" ]; then
    DESKTOP_SHORTCUT="$DESKTOP_PHYSICAL/devops-manager.desktop"
    echo "$DESKTOP_ENTRY" > "$DESKTOP_SHORTCUT"
    chmod +x "$DESKTOP_SHORTCUT"
    echo "Acceso directo en escritorio: $DESKTOP_SHORTCUT"
fi

echo ""
