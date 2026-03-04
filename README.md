# DevOps Manager

**DevOps Manager** es una herramienta de escritorio desarrollada en Python con una interfaz gráfica (basada en `customtkinter`) diseñada para facilitar la administración agrupadad de múltiples repositorios de desarrollo. 

Esta aplicación te permite visualizar, configurar y ejecutar tus proyectos desde un único panel centralizado, simplificando las tareas repetitivas y estandarizando la gestión de tus entornos de desarrollo.

## Características Principales

* **Gestión Centralizada de Repositorios:** Visualiza el estado de tus repositorios, agrúpalos y aplica comandos personalizados.
* **Perfiles de Configuración (Exportar / Importar):** Guarda el estado de tus configuraciones, presintonías de bases de datos y archivos modificados (`.yml`, `.ts`, etc.) para compartirlos y restaurarlos fácilmente.
* **Presintonías de Bases de Datos:** Aplica configuraciones específicas de base de datos a tus proyectos con un clic.
* **Consolidación de Logs:** Visualiza los logs de ejecución de las diferentes herramientas y repositorios en una pestaña dedicada.
* **Internacionalización (i18n):** Soporte multi-idioma con detección dinámica de archivos de lenguaje.
* **Interfaz Moderna e Intuitiva:** Rediseñada con tarjetas de repositorios y botones con tooltips.

## Requisitos Previos

* **Python 3.8+** instalado en tu sistema.
* **Git** instalado e incluido en el PATH (para la gestión de repositorios mediante `GitPython`).

## Instalación

Para asegurar que las dependencias de este proyecto (como `customtkinter`, `PyYAML`, `Pillow`, etc.) no interfieran con otros proyectos de Python en tu sistema, se recomienda llevar a cabo la instalación utilizando un **entorno virtual (venv)**.

### Opción 1: Instalación Automática (Recomendada)

Hemos incluido scripts preparados para inicializar el entorno virtual y descargar todas las dependencias de manera automática:

**Para Windows:**
Haz doble clic sobre el archivo `install.bat` o ejecútalo desde tu consola:
```cmd
install.bat
```

**Para Linux / macOS:**
Dale permisos de ejecución al script y lánzalo:
```bash
chmod +x install.sh
./install.sh
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
* **Windows:** Ejecuta `run.bat`
* **Linux/macOS:** Ejecuta `./run.sh`

### Ejecución Manual

Desde la terminal, con el entorno virtual ya activado:
```bash
python main.py
```

Al abrirla, la aplicación autodetectará por defecto el espacio de trabajo basado en la carpeta principal superior (o puedes especificar una ruta al hacer el lanzamiento: `python main.py /ruta/a/tu/workspace`).

## Configuración

La configuración propia de la herramienta se guarda en `devops_manager_config.json`, donde se almacena el estado visual actual, últimos comandos introducidos, configuración de las bases de datos y la ruta de tu espacio de trabajo.
