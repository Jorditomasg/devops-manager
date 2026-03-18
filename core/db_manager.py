"""
db_manager.py — Manage local MySQL via Docker, Flyway seeds.
"""
from __future__ import annotations
import subprocess
import os
from typing import Optional, Callable

LogCallback = Optional[Callable[[str], None]]


def is_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(['docker', 'info'],
                                capture_output=True, text=True, timeout=10,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def is_container_running(container_name: str) -> bool:
    """Check if a specific docker container is running."""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        return container_name in result.stdout
    except (subprocess.SubprocessError, OSError):
        return False


def get_running_containers(project_prefix: str = '') -> list[dict]:
    """List running containers, optionally filtered by project prefix."""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}\t{{.Status}}\t{{.Ports}}'],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        containers = []
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split('\t')
                if len(parts) >= 2:
                    name = parts[0]
                    if project_prefix and project_prefix not in name:
                        continue
                    containers.append({
                        'name': name,
                        'status': parts[1] if len(parts) > 1 else '',
                        'ports': parts[2] if len(parts) > 2 else '',
                    })
        return containers
    except (subprocess.SubprocessError, OSError):
        return []

def parse_compose_services(compose_file: str) -> list[dict]:
    """Parse a docker-compose file and return a list of defined services."""
    try:
        import yaml
        with open(compose_file, 'r', encoding='utf-8') as f:
            compose = yaml.safe_load(f) or {}

        services_dict = compose.get('services', {})
        services_list = []
        for name, config in services_dict.items():
            ports_raw = config.get('ports', [])
            ports = [str(p) for p in ports_raw] if ports_raw else []

            depends_on_raw = config.get('depends_on', [])
            depends_on = []
            if isinstance(depends_on_raw, list):
                depends_on = depends_on_raw
            elif isinstance(depends_on_raw, dict):
                depends_on = list(depends_on_raw.keys())

            services_list.append({
                'name': name,
                'image': config.get('image', config.get('build', 'unknown')),
                'ports': ports,
                'depends_on': depends_on
            })
        return services_list
    except Exception as e:
        print(f"Error parsing {compose_file}: {e}")
        return []

def get_compose_service_status(compose_file: str) -> dict:
    """Get the status of all services in a docker-compose file."""
    try:
        fname = os.path.basename(compose_file)
        cwd = os.path.dirname(compose_file)
        
        # Using docker-compose ps --services --filter "status=running" is cleaner 
        # but --format json isn't well supported in older compose v1.
        # So we'll parse standard ps output.
        result = subprocess.run(
            ['docker-compose', '-f', fname, 'ps'],
            capture_output=True, text=True, timeout=10, cwd=cwd,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        # Simple heuristic: map actual container names back to services later
        # However, a more robust way for compose is asking specifically for services.
        # Let's use `docker-compose -f fname ps --services` to see what is defined,
        # then map running ones. Wait, `docker-compose config --services` gives defined ones.
        # Let's extract status correctly by parsing the table.
        status_map = {}
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # Standard compose v1 output table format: Name, Command, State, Ports
            for line in lines[2:]:  # skip header and separator
                if not line.strip(): continue
                parts = line.split()
                if not parts: continue
                container_name = parts[0]
                
                # Guess the service name from container name (usually project_service_index)
                # But docker-compose v1 puts the state in the 3rd or 4th column, usually "Up", "Exit..." 
                state = "exited"
                if "Up" in line or "running" in line.lower():
                    state = "running"
                status_map[container_name] = state
                
        # To map containers to services properly:
        # We can ask for running containers for this specific project
        running_srv_result = subprocess.run(
           ['docker-compose', '-f', fname, 'ps', '--services', '--filter', 'status=running'],
           capture_output=True, text=True, timeout=10, cwd=cwd,
           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        running_services = []
        if running_srv_result.returncode == 0:
            running_services = running_srv_result.stdout.strip().splitlines()
            
        # We return a dict {service_name: "running" | "stopped"}
        # Services not in running_services are considered stopped.
        all_services = [s['name'] for s in parse_compose_services(compose_file)]
        final_map = {}
        for srv in all_services:
            final_map[srv] = "running" if srv in running_services else "stopped"
            
        return final_map
    except Exception as e:
        print(f"Error checking status for {compose_file}: {e}")
        return {}

def docker_compose_logs(compose_file: str, service_name: str, tail: int = 100) -> str:
    """Get the tail logs for a specific service."""
    try:
        fname = os.path.basename(compose_file)
        cwd = os.path.dirname(compose_file)
        result = subprocess.run(
            ['docker-compose', '-f', fname, 'logs', '--tail', str(tail), service_name],
            capture_output=True, text=True, timeout=10, cwd=cwd,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        return result.stdout.strip() + "\n" + result.stderr.strip()
    except Exception as e:
        return f"Error retrieving logs: {e}"


def docker_compose_up(compose_file: str, services: list = None,
                       log: LogCallback = None) -> tuple[bool, str]:
    """Start services from a docker-compose file."""
    try:
        fname = os.path.basename(compose_file)
        cwd = os.path.dirname(compose_file)

        cmd = ['docker-compose', '-f', fname, 'up', '-d']
        if services:
            cmd.extend(services)

        if log:
            svc_str = ', '.join(services) if services else 'all'
            log(f"[docker] Starting {svc_str} from {fname}...")

        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=cwd, timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        msg = result.stdout.strip() + '\n' + result.stderr.strip()

        if log:
            if result.returncode == 0:
                log(f"[docker] {fname}: Services started")
            else:
                log(f"[docker] {fname}: FAILED - {msg}")

        return result.returncode == 0, msg.strip()
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[docker] Error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[docker] Unexpected error: {e}")
        return False, str(e)


def docker_compose_down(compose_file: str, log: LogCallback = None) -> tuple[bool, str]:
    """Stop services from a docker-compose file."""
    try:
        fname = os.path.basename(compose_file)
        cwd = os.path.dirname(compose_file)

        cmd = ['docker-compose', '-f', fname, 'down']

        if log:
            log(f"[docker] Stopping services from {fname}...")

        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=cwd, timeout=60,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        msg = result.stdout.strip() + '\n' + result.stderr.strip()

        if log:
            log(f"[docker] {fname}: Services stopped")

        return result.returncode == 0, msg.strip()
    except (subprocess.SubprocessError, OSError) as e:
        if log:
            log(f"[docker] Error: {e}")
        return False, str(e)
    except Exception as e:
        if log:
            log(f"[docker] Unexpected error: {e}")
        return False, str(e)


def _get_compose_file(infra_path: str) -> str:
    import glob
    files = glob.glob(os.path.join(infra_path, 'docker-compose*.yml')) + \
            glob.glob(os.path.join(infra_path, 'docker-compose*.yaml'))
    if not files:
        return ""
    # Prefer mysql one if multiple exist, else first
    return next((f for f in files if 'mysql' in f), files[0])

def start_mysql(infra_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Start MySQL using a docker-compose file from the infra repo."""
    compose_file = _get_compose_file(infra_path)
    if not compose_file:
        msg = f"No docker-compose file found in {infra_path}"
        if log:
            log(f"[db] {msg}")
        return False, msg
    return docker_compose_up(compose_file, ['mysqldb'], log)


def stop_mysql(infra_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Stop MySQL container."""
    compose_file = _get_compose_file(infra_path)
    if not compose_file:
        return False, "No docker-compose file found"
    return docker_compose_down(compose_file, log)


def _detect_flyway_services(compose_file: str) -> list[str]:
    """Auto-detect flyway service names from a docker-compose file."""
    try:
        import yaml
        with open(compose_file, 'r', encoding='utf-8') as f:
            compose = yaml.safe_load(f) or {}
        services = compose.get('services', {}) or {}
        return [name for name in services if 'flyway' in name.lower()]
    except (OSError, yaml.YAMLError):
        return []


def run_flyway_seeds(infra_path: str, log: LogCallback = None) -> tuple[bool, str]:
    """Run all Flyway migration services from the docker-compose file."""
    compose_file = _get_compose_file(infra_path)
    if not compose_file:
        msg = "No docker-compose file found"
        if log:
            log(f"[db] {msg}")
        return False, msg

    flyway_services = _detect_flyway_services(compose_file)
    if not flyway_services:
        msg = "No flyway services found in docker-compose.mysql.yml"
        if log:
            log(f"[db] {msg}")
        return False, msg

    if log:
        log(f"[db] Running Flyway migrations: {', '.join(flyway_services)}...")

    return docker_compose_up(compose_file, flyway_services, log)


def is_mysql_running(infra_path: str = '') -> bool:
    """Check if MySQL container from boa2-backend-local is running."""
    containers = get_running_containers()
    for c in containers:
        name = c.get('name', '')
        if 'mysql' in name.lower() or 'mysqldb' in name.lower():
            return True
    return False


def start_service_compose(compose_file: str, service_name: str,
                           log: LogCallback = None) -> tuple[bool, str]:
    """Start a specific service from a docker-compose file."""
    return docker_compose_up(compose_file, [service_name], log)


def stop_service_compose(compose_file: str, service_name: str = None,
                          log: LogCallback = None) -> tuple[bool, str]:
    """Stop a specific service from a docker-compose file."""
    if service_name:
        try:
            fname = os.path.basename(compose_file)
            cwd = os.path.dirname(compose_file)
            cmd = ['docker-compose', '-f', fname, 'stop', service_name]
            if log:
                log(f"[docker] Stopping {service_name}...")
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    cwd=cwd, timeout=60,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            msg = result.stdout.strip() + '\n' + result.stderr.strip()
            return result.returncode == 0, msg.strip()
        except (subprocess.SubprocessError, OSError) as e:
            if log:
                log(f"[docker] Error stopping {service_name}: {e}")
            return False, str(e)
        except Exception as e:
            if log:
                log(f"[docker] Unexpected error stopping {service_name}: {e}")
            return False, str(e)
    else:
        return docker_compose_down(compose_file, log)
