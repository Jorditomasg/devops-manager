#!/bin/bash
cd "$(dirname "$0")/../.."
if [ "$#" -eq 0 ]; then
    echo "Usa: ./scripts/linux/run-compiled.sh <ruta_del_workspace>"
    exit 1
fi

./dist/main.dist/devops-manager "$1" &
