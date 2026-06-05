"""instance_manager.py — Single-instance coordination via a loopback control socket.

Each running app registers a small JSON file (``<pid>.json``) in a shared registry
directory and listens on an ephemeral loopback port. A starting instance can then:

* discover other LIVE instances managing the SAME workspace (``find_other_instances``),
* ask them to close gracefully (``send_shutdown`` → the target runs its normal
  ``_on_close``, stopping every managed service and saving state), and
* poll until they are gone (``still_alive``).

Liveness is proven by an actual PING over the socket, so registry files left behind
by a crashed instance are detected as stale and pruned automatically.
"""
import os
import glob
import json
import socket
import tempfile
import threading
import logging

_REGISTRY_DIRNAME = "devops_manager_instances"
_HOST = "127.0.0.1"
_PING = b"PING"
_PONG = b"PONG"
_SHUTDOWN = b"SHUTDOWN"
_OK = b"OK"
_SOCK_TIMEOUT = 1.0   # seconds for a single request/response round-trip


class InstanceManager:
    """Coordinates discovery and graceful shutdown between app instances."""

    def __init__(self, workspace: str):
        # Normalised so two paths that differ only in case/separators still match.
        self.workspace = os.path.normcase(os.path.abspath(workspace))
        self.pid = os.getpid()
        self.registry_dir = os.path.join(tempfile.gettempdir(), _REGISTRY_DIRNAME)
        self._own_file = os.path.join(self.registry_dir, f"{self.pid}.json")
        self._server_sock: socket.socket | None = None
        self._server_thread: threading.Thread | None = None
        self._on_shutdown = None
        self._stop = False
        try:
            os.makedirs(self.registry_dir, exist_ok=True)
        except OSError:
            logging.exception("Could not create instance registry dir")

    # ── Discovery ────────────────────────────────────────────────────────────

    def find_other_instances(self) -> list[dict]:
        """Return live instances (other than this one) managing the same workspace.

        Stale registry files (own pid, unparsable, or whose port no longer answers)
        are pruned as a side effect."""
        found = []
        for path in glob.glob(os.path.join(self.registry_dir, "*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._safe_remove(path)
                continue
            if data.get("pid") == self.pid:
                continue
            if os.path.normcase(str(data.get("workspace", ""))) != self.workspace:
                continue
            port = data.get("port")
            if not port or not self._ping(port):
                self._safe_remove(path)   # crashed instance — clean it up
                continue
            data["_file"] = path
            found.append(data)
        return found

    def _ping(self, port: int) -> bool:
        try:
            with socket.create_connection((_HOST, port), timeout=_SOCK_TIMEOUT) as s:
                s.sendall(_PING)
                return s.recv(16).strip() == _PONG
        except OSError:
            return False

    def send_shutdown(self, instances: list[dict]) -> None:
        """Fire a graceful-shutdown request at each instance (does not wait)."""
        for inst in instances:
            port = inst.get("port")
            if not port:
                continue
            try:
                with socket.create_connection((_HOST, port), timeout=_SOCK_TIMEOUT) as s:
                    s.sendall(_SHUTDOWN)
                    s.recv(16)
            except OSError:
                pass

    def still_alive(self, instances: list[dict]) -> list[dict]:
        """Subset of ``instances`` whose control port still answers a PING."""
        return [i for i in instances if i.get("port") and self._ping(i["port"])]

    # ── Server ───────────────────────────────────────────────────────────────

    def start_server(self, on_shutdown) -> int:
        """Bind an ephemeral loopback port, register this instance, and start
        serving control requests on a daemon thread. Returns the port."""
        self._on_shutdown = on_shutdown
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((_HOST, 0))
        sock.listen(5)
        self._server_sock = sock
        port = sock.getsockname()[1]
        self._write_registry(port)
        self._server_thread = threading.Thread(
            target=self._serve, name="instance-control", daemon=True
        )
        self._server_thread.start()
        return port

    def _serve(self) -> None:
        sock = self._server_sock
        while not self._stop and sock is not None:
            try:
                conn, _ = sock.accept()
            except OSError:
                break   # socket closed during cleanup
            try:
                conn.settimeout(_SOCK_TIMEOUT)
                data = conn.recv(16).strip()
                if data == _PING:
                    conn.sendall(_PONG)
                elif data == _SHUTDOWN:
                    conn.sendall(_OK)
                    conn.close()
                    if self._on_shutdown:
                        self._on_shutdown()
                    break
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _write_registry(self, port: int) -> None:
        try:
            with open(self._own_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"pid": self.pid, "port": port, "workspace": self.workspace}, f
                )
        except OSError:
            logging.exception("Could not write instance registry file")

    def cleanup(self) -> None:
        """Stop serving and remove this instance's registry file."""
        self._stop = True
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        self._safe_remove(self._own_file)

    @staticmethod
    def _safe_remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass
