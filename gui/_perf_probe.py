"""[DEBUG-perf] TEMPORARY instrumentation for performance diagnosis.

Probes:
  perf_snapshot   — periodic snapshot of threads, after() callbacks, RSS, queue
  time_restore    — context manager that times tray-restore latency
  log_drain       — track stdout/stderr drain bursts

Remove this file and `grep -r '[DEBUG-perf]' gui/` to clean all call sites.

Output goes to:
  - sys.__stdout__ (visible if launched from scripts/win/run.bat console)
  - perf_probe.log at project root (always, survives scripts/win/run.vbs silent launch)
"""
from __future__ import annotations
import os
import sys
import time
import threading

_BOOT_TIME = time.time()
_SNAPSHOT_COUNTER = {"n": 0}
_DRAIN_COUNTER = {"total": 0, "max": 0}
_RESTORE_COUNTER = {"n": 0}

_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'perf_probe.log',
)


def _write(line: str) -> None:
    """Write to original stdout (console) AND a log file.
    Bypasses StreamRedirector so it does NOT re-enter the global log queue."""
    try:
        if sys.__stdout__ is not None:
            sys.__stdout__.write(line + "\n")
            sys.__stdout__.flush()
    except Exception:
        pass
    try:
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        pass


def _mem_mb() -> float:
    """Resident set size in MB. Best effort, no external deps."""
    try:
        if sys.platform == 'win32':
            import ctypes

            class _PMC(ctypes.Structure):
                _fields_ = [
                    ('cb', ctypes.c_ulong),
                    ('PageFaultCount', ctypes.c_ulong),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t),
                ]
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(pmc), pmc.cb,
            )
            return pmc.WorkingSetSize / (1024 * 1024)
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return -1.0


def _after_count(root) -> int:
    """Number of pending Tk after() callbacks."""
    try:
        info = root.tk.call('after', 'info')
        if isinstance(info, str):
            return len(info.split()) if info else 0
        return len(info)
    except Exception:
        return -1


def perf_snapshot(app, force: bool = False) -> None:
    """One snapshot line. Call from _do_update_tray_status (5s); fires every 6th call (~30s)."""
    _SNAPSHOT_COUNTER["n"] += 1
    if not force and _SNAPSHOT_COUNTER["n"] % 6 != 0:
        return

    uptime = time.time() - _BOOT_TIME
    threads = threading.active_count()
    after_n = _after_count(app)
    mem = _mem_mb()
    qsize = -1
    buf_len = -1
    try:
        qsize = app._global_log_queue.qsize()
        buf_len = len(app._global_log_buffer)
    except Exception:
        pass
    cards = len(getattr(app, '_repo_cards', []))

    _write(
        f"[DEBUG-perf] t={uptime:.0f}s threads={threads} after={after_n} "
        f"rss={mem:.1f}MB cards={cards} queue={qsize} buf={buf_len} "
        f"drain_max={_DRAIN_COUNTER['max']} drain_total={_DRAIN_COUNTER['total']}"
    )


class time_restore:
    """Context manager: time the tray restore path (ms)."""

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        _RESTORE_COUNTER["n"] += 1
        dt = (time.perf_counter() - self._t0) * 1000.0
        _write(f"[DEBUG-perf] restore#{_RESTORE_COUNTER['n']} took={dt:.1f}ms")


def log_drain(count: int) -> None:
    """Record one stdout/stderr drain. Print only on surprising bursts."""
    if count <= 0:
        return
    _DRAIN_COUNTER["total"] += count
    if count > _DRAIN_COUNTER["max"]:
        _DRAIN_COUNTER["max"] = count
    if count > 100:
        _write(f"[DEBUG-perf] drain_burst count={count}")
