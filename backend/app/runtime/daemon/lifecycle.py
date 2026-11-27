"""Daemon lifecycle: single instance, process-tree ownership and the run loop.

Windows uses a named mutex plus a `KILL_ON_JOB_CLOSE` job object; other
platforms fall back to an advisory file lock and process groups so the module
stays importable and unit-testable on Linux CI. The Windows path is the only
one that has been validated (see ADR 0007).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .contract import DEFAULT_PIPE_NAME, load_contract
from .control_ipc import ControlPlane, DaemonInfo, PipeServer
from .supervisor import DEFAULT_ROLES, Child, Process, Role, Supervisor

DEFAULT_MUTEX = "Global\\CareerLens.Daemon"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8123/health/live"
DEFAULT_VERSION = "0.2.0-m2"


@dataclass
class DaemonConfig:
    api_exe: str
    version: str = DEFAULT_VERSION
    pipe_name: str = DEFAULT_PIPE_NAME
    health_url: str = DEFAULT_HEALTH_URL
    base_env: dict[str, str] = field(default_factory=dict)
    ready_timeout: float = 60.0
    tick_seconds: float = 0.4


class SingleInstance:
    """Per-user single-instance guard."""

    def __init__(self, name: str = DEFAULT_MUTEX) -> None:
        self.name = name
        self._handle: object | None = None
        self._lock_file = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows()

        import fcntl

        path = os.path.join(tempfile.gettempdir(), f"{self.name.replace(chr(92), '-')}.lock")
        self._lock_file = open(path, "w", encoding="utf-8")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_file.close()
            self._lock_file = None
            return False
        self._lock_file.write(str(os.getpid()))
        self._lock_file.flush()
        return True

    def _acquire_windows(self) -> bool:  # pragma: no cover - Windows-only
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        handle = kernel32.CreateMutexW(None, False, self.name)
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if not handle or already:
            if handle:
                kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if sys.platform == "win32":  # pragma: no cover - Windows-only
            if self._handle:
                import ctypes

                ctypes.WinDLL("kernel32").CloseHandle(self._handle)
                self._handle = None
            return
        if self._lock_file:
            self._lock_file.close()
            self._lock_file = None


class ProcessTree:
    """Kills every supervised child when the daemon dies unexpectedly."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self) -> None:
        self._job = None

    def attach(self) -> bool:
        if sys.platform != "win32":
            return False
        return self._attach_windows()

    def _attach_windows(self) -> bool:  # pragma: no cover - Windows-only
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False
        self._job = job
        info = _extended_limit_info()
        if not kernel32.SetInformationJobObject(
            job, self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
            ctypes.sizeof(info)
        ):
            return False
        process = kernel32.OpenProcess(0x1FFFFF, False, kernel32.GetCurrentProcessId())
        if not process:
            return False
        assigned = kernel32.AssignProcessToJobObject(job, process)
        kernel32.CloseHandle(process)
        return bool(assigned)

    def close(self) -> None:
        # 故意不关闭 job 句柄：daemon 在 job 内，KILL_ON_JOB_CLOSE 会把自己杀掉，
        # 掩盖优雅退出路径；进程退出时由内核回收该句柄。
        self._job = None


def _extended_limit_info():  # pragma: no cover - ctypes struct wiring
    import ctypes
    import ctypes.wintypes as wintypes

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = ProcessTree.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    return info


def build_spawner(config: DaemonConfig) -> Callable[[Role], Process]:
    def spawn(role: Role) -> Process:
        env = {**os.environ, **config.base_env, role.env_flag: "1"}
        return subprocess.Popen(
            [config.api_exe],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
        )

    return spawn


def probe_health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_ready(health: Callable[[], bool], timeout: float, sleep: Callable[[float], None]) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if health():
            return True
        sleep(0.5)
    return False


def run_daemon(config: DaemonConfig, *, log: Callable[[str], None] = print) -> int:
    lock = SingleInstance()
    if not lock.acquire():
        log("DAEMON_ALREADY_RUNNING")
        return 3

    tree = ProcessTree()
    tree.attach()
    contract = load_contract()
    supervisor = Supervisor(
        DEFAULT_ROLES,
        spawn=build_spawner(config),
        health=lambda: probe_health(config.health_url),
    )
    info = DaemonInfo(
        version=config.version,
        instance_id=str(uuid.uuid4()),
        started_at=time.time(),
        pid=os.getpid(),
        roles=tuple(child.role.name for child in supervisor.children.values()),
    )
    ready = threading.Event()
    plane = ControlPlane(
        contract, supervisor, info, backend_url=config.health_url, ready=ready.is_set
    )
    stop_requested = threading.Event()

    def request_stop() -> None:
        stop_requested.set()

    server = None
    if sys.platform == "win32":
        server = PipeServer(plane, pipe_name=config.pipe_name, on_stop=request_stop)
        server.open()

    try:
        for event in supervisor.start_all():
            log(f"{event.kind} {event.role} {event.detail}")
        if wait_ready(supervisor.healthy, config.ready_timeout, time.sleep):
            ready.set()
        log(f"daemon.ready pid={os.getpid()}")
        if server is not None:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        while not stop_requested.is_set():
            for event in supervisor.tick():
                log(f"{event.kind} {event.role} {event.detail}")
            time.sleep(config.tick_seconds)
        return 0
    finally:
        supervisor.stop()
        if server is not None:
            server.wake()
            server.close()
        tree.close()
        lock.release()


__all__ = [
    "Child",
    "DaemonConfig",
    "ProcessTree",
    "SingleInstance",
    "build_spawner",
    "probe_health",
    "run_daemon",
    "wait_ready",
]
