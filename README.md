# DevOps Manager

**DevOps Manager** es una herramienta de escritorio desarrollada en Python con una interfaz gráfica (basada en `customtkinter`) diseñada para facilitar la administración agrupada de múltiples repositorios de desarrollo. 

Esta aplicación te permite visualizar, configurar y ejecutar tus proyectos desde un único panel centralizado, simplificando las tareas repetitivas y estandarizando la gestión de tus entornos de desarrollo.

## Características Principales

* **Gestión Centralizada de Repositorios:** Visualiza el estado de tus repositorios, agrúpalos y aplica comandos personalizados.
* **Perfiles de Configuración (Exportar / Importar):** Guarda el estado de tus configuraciones y archivos modificados (`.yml`, `.ts`, etc.) para compartirlos y restaurarlos fácilmente.
* **Gestión de Docker Compose:** Inicia, detiene y monitoriza servicios de docker-compose por tarjeta de repositorio, con integración en perfiles para auto-arranque.
* **Consolidación de Logs:** Visualiza los logs de ejecución de las diferentes herramientas y repositorios en una pestaña dedicada.
* **Interfaz Moderna e Intuitiva:** Tarjetas de repositorios con acordeón expandible, tooltips y tema visual personalizable.

## Requisitos Previos

* **Python 3.8+** instalado en tu sistema.
* **Git** instalado e incluido en el PATH (para la gestión de repositorios mediante `GitPython`).

## Instalación

Para asegurar que las dependencias de este proyecto (como `customtkinter`, `PyYAML`, `Pillow`, etc.) no interfieran con otros proyectos de Python en tu sistema, se recomienda llevar a cabo la instalación utilizando un **entorno virtual (venv)**.

### Opción 1: Instalación Automática (Recomendada)

Hemos incluido scripts preparados para inicializar el entorno virtual y descargar todas las dependencias de manera automática:

**Para Windows:**
Haz doble clic sobre el archivo `scripts\install.bat` o ejecútalo desde tu consola:
```cmd
scripts\install.bat
```

**Para Linux / macOS:**
Dale permisos de ejecución al script y lánzalo:
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

### Opción 2: Instalación Manual

Si prefieres realizar los pasos manualmente en tu terminal:

1. **Crear el entorno virtual:**
   ```bash
   python -m venv .venv
   ```

2. **Activar el entorno virtual:**
   * **Windows:** `.venv\Scripts\activate`
   * **Linux/macOS:** `source .venv/bin/activate`

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

## Uso

Una vez instalado, asegúrate de tener activo tu entorno virtual antes de ejecutar la aplicación.

### Ejecución Rápida

Puedes utilizar los scripts predefinidos para iniciar la aplicación cómodamente:
* **Windows:** Ejecuta `scripts\run.bat`
* **Linux/macOS:** Ejecuta `./scripts/run.sh`

### Ejecución Manual

Desde la terminal, con el entorno virtual ya activado:
```bash
python main.py
```

Al abrirla, la aplicación autodetectará por defecto el espacio de trabajo basado en la carpeta principal superior (o puedes especificar una ruta al hacer el lanzamiento: `python main.py /ruta/a/tu/workspace`).

## Configuración

La configuración propia de la herramienta se guarda en `devops_manager_config.json`, donde se almacena el estado visual actual, últimos comandos introducidos y la ruta de tu espacio de trabajo.

## Distribución / Releases

Los ejecutables firmados se generan automáticamente mediante GitHub Actions (`.github/workflows/build-and-sign.yml`):

1. Crea y sube un tag con el formato `v*` (por ejemplo `v1.2.0`) para disparar el pipeline.
2. El workflow compila un `.exe` standalone con **Nuitka** sobre Windows.
3. El binario se firma automáticamente a través de **SignPath**.
4. El `.exe` firmado se adjunta al **GitHub Release** correspondiente al tag.
