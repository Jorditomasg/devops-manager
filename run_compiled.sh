#!/bin/bash
if [ "$#" -eq 0 ]; then
    echo "Usa: ./run_compiled.sh <ruta_del_workspace>"
    exit 1
fi

./dist/main.dist/devops-manager "$1" &
