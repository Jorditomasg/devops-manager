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

## Añadir un Nuevo Tipo de Repositorio

No se necesita tocar código. Basta con crear un archivo YAML en `config/repo_types/` y la aplicación lo detectará automáticamente en el siguiente arranque.

### Plantilla completa

```yaml
# config/repo_types/mi-tipo.yml

# Identificador interno único (snake_case o kebab-case)
type: "mi-tipo"

# Prioridad de detección. Si un repo coincide con varios tipos, gana el de mayor valor.
# Rangos orientativos: spring-boot=60, angular=40, react=30, nx=50, docker-infra=0
priority: 10

# ── DETECCIÓN ─────────────────────────────────────────────────────────────────
detection:
  # Ficheros que DEBEN existir en la raíz del repo (AND lógico)
  required_files:
    - "package.json"
  # Ficheros cuya presencia EXCLUYE este tipo (útil para evitar falsos positivos)
  exclude_files:
    - "angular.json"

heuristics:
  # Directorios que deben existir (AND lógico)
  must_have_directories:
    - "src"
  # Patrones glob que deben encontrarse en algún fichero de la raíz
  must_match_patterns:
    - "vite.config.*"

# ── COMANDOS ──────────────────────────────────────────────────────────────────
commands:
  install_cmd: "npm install"
  # Comando para reinstalar (limpia artefactos antes)
  reinstall_cmd: "rmdir /s /q node_modules & npm install"   # Windows
  start_cmd:   "npm run dev"
  # Sobreescrituras por SO (opcional; si se omiten se usa start_cmd)
  windows_start_cmd: "npm run dev"
  unix_start_cmd:    "npm run dev"
  stop_cmd: ""          # Vacío = el proceso se mata con SIGTERM
  # Flag que se añade al start_cmd para seleccionar perfil/entorno
  profile_flag: "--mode "
  # Regex que indica en los logs que el servicio ya está listo
  ready_pattern: "ready in|Local:.*http"
  # Regex que detecta un fallo fatal en los logs
  error_pattern: "Error:|failed to"

# ── FICHEROS DE ENTORNO / CONFIGURACIÓN ───────────────────────────────────────
env_files:
  # Directorio donde viven los ficheros de config (relativo a la raíz del repo)
  default_dir: "."
  # Tipo de escritor de config: "spring" | "angular" | "raw"
  config_writer_type: "raw"
  # Patrones que NO se incluyen en el snapshot de perfil al hacer pull
  pull_ignore_patterns:
    - ".env*"
  # Fichero principal que se abre al editar la configuración
  main_config_filename: ".env"
  # Patrones glob para listar todos los ficheros de configuración disponibles
  patterns:
    - ".env"
    - ".env.*"
  # Directorios ignorados al buscar ficheros de configuración
  exclude_dirs:
    - "node_modules"
    - ".git"
    - "dist"

# ── INTERFAZ ──────────────────────────────────────────────────────────────────
ui:
  # Emoji o carácter que aparece en la cabecera de la tarjeta
  icon: "⚡"
  # Color del borde/acento de la tarjeta (hex)
  color: "#a855f7"
  # Etiquetas del selector de fichero de config en el panel expandido
  selectors:
    - label: "Env:"
  install:
    # Directorio cuya presencia indica que las dependencias ya están instaladas
    check_dirs: ["node_modules"]
    label_missing: "Install"
    label_ok: "Reinstall ✓"
    tooltip: "npm install"
    status_label_deps_missing: "⚠ Falta instalar"

# ── CARACTERÍSTICAS OPCIONALES ────────────────────────────────────────────────
features:
  # Muestra selector de versión de Java en el panel expandido
  # - "java_version"
  # Añade checkboxes de perfiles de Docker Compose
  # - "docker_checkboxes"
```

### Campos obligatorios mínimos

| Campo | Descripción |
|---|---|
| `type` | Identificador único del tipo |
| `priority` | Orden de preferencia en la detección |
| `detection.required_files` | Lista de ficheros que deben existir (puede ser `[]`) |
| `commands.start_cmd` | Comando de arranque del servicio |
| `ui.icon` | Icono de la tarjeta |
| `ui.color` | Color de acento (hex) |

El resto de campos son opcionales: si se omiten, la funcionalidad asociada sencillamente no aparece en la tarjeta.

## Distribución / Releases

Los ejecutables firmados se generan automáticamente mediante GitHub Actions (`.github/workflows/build-and-sign.yml`):

1. Crea y sube un tag con el formato `v*` (por ejemplo `v1.2.0`) para disparar el pipeline.
2. El workflow compila un `.exe` standalone con **Nuitka** sobre Windows.
3. El binario se firma automáticamente a través de **SignPath**.
4. El `.exe` firmado se adjunta al **GitHub Release** correspondiente al tag.
