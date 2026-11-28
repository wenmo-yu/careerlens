"""Daemon control plane: contract-driven command dispatch plus the pipe server.

`ControlPlane.dispatch` is pure Python so it can be tested on any platform.
`PipeServer` holds the Windows-only plumbing and imports nothing at module
level, which keeps `import app.runtime.daemon.control_ipc` safe everywhere.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from .contract import Contract
from .supervisor import Supervisor

# One control frame is a single line of JSON. The pipe server reads up to 64 KiB
# per message; the character cap here is the same budget expressed in characters
# so the pure-Python dispatcher can enforce it on any platform.
MAX_FRAME_CHARS = 64 * 1024


@dataclass(frozen=True)
class DaemonInfo:
    version: str
    instance_id: str
    started_at: float
    pid: int
    roles: tuple[str, ...]


@dataclass
class Session:
    handshaken: bool = False


def error(code: str, message: str, **extra: object) -> dict:
    return {"ok": False, "code": code, "message": message, **extra}


class ControlPlane:
    def __init__(
        self,
        contract: Contract,
        supervisor: Supervisor,
        info: DaemonInfo,
        *,
        backend_url: str,
        ready: Callable[[], bool] | None = None,
    ) -> None:
        self.contract = contract
        self.supervisor = supervisor
        self.info = info
        self.backend_url = backend_url
        self.ready = ready or (lambda: True)

    # --- helpers -------------------------------------------------------------
    def _status(self) -> dict:
        return {
            "daemon": {
                "pid": self.info.pid,
                "version": self.info.version,
                "uptime_s": round(self.supervisor.now() - self.info.started_at, 1),
            },
            "backend": {"healthy": self.supervisor.healthy(), "url": self.backend_url},
            "children": self.supervisor.status(),
        }

    @staticmethod
    def _decode(line: str) -> tuple[str, dict, str | None]:
        """Decode one control frame.

        The published contract uses one JSON object per line. The positional
        form (`hello 1`, `restart worker`) is kept as a deprecated compatibility
        path for the M1/M2 probe, but new clients must send JSON.
        """

        text = line.strip()
        if not text:
            return "", {}, None
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                return "", {}, "invalid_json"
            if not isinstance(payload, dict):
                return "", {}, "invalid_json"
            verb = str(payload.get("command", "")).lower()
            params = payload.get("params") or {}
            if not isinstance(params, dict):
                return verb, {}, "invalid_params_object"
            return verb, params, None
        parts = text.split()
        verb = parts[0].lower()
        params: dict[str, object] = {}
        if verb == "hello" and len(parts) > 1:
            params["protocol"] = parts[1]
            if len(parts) > 2:
                params["client"] = parts[2]
        elif verb == "restart" and len(parts) > 1:
            params["role"] = parts[1]
        return verb, params, None

    # --- dispatch ------------------------------------------------------------
    def dispatch(self, line: str, session: Session) -> tuple[dict, Session]:
        # Defence in depth: the pipe uses a 64 KiB message buffer, but a client
        # can hand us a long line through the compatibility path too. Rejecting
        # here keeps the limit explicit and testable off-Windows.
        if len(line) > MAX_FRAME_CHARS:
            return (
                error(
                    "frame_too_large",
                    "control frame exceeds the accepted size",
                    limit=MAX_FRAME_CHARS,
                ),
                session,
            )
        verb, params, decode_error = self._decode(line)
        if decode_error:
            return error(decode_error, "invalid control frame"), session
        if not verb:
            return error("invalid_params", "empty command"), session
        spec = self.contract.command(verb)

        if verb == "hello":
            return self._hello(params, session)
        if not session.handshaken:
            return error("not_ready", "send hello before other commands"), session
        if spec is None:
            return error("unknown_command", f"unknown command: {verb}"), session
        missing = self._missing(spec.required_params, params)
        if missing:
            return error("invalid_params", "missing command arguments", missing=missing), session
        if verb == "ping":
            return {"ok": True, "pong": True}, session
        if not self.ready():
            return error("not_ready", "daemon is still starting"), session
        if verb == "status":
            return {"ok": True, **self._status()}, session
        if verb == "restart":
            role = str(params["role"]).lower()
            if role not in self.contract.restart_roles:
                return error("unknown_role", f"unknown role: {role}"), session
            self.supervisor.restart(role)
            return {"ok": True, "restarting": role}, session
        if verb == "stop":
            return {"ok": True, "stopping": True}, session
        return error("unknown_command", f"unknown command: {verb}"), session

    @staticmethod
    def _missing(required: tuple[str, ...], params: dict) -> list[str]:
        return [name for name in required if name not in params or params[name] in (None, "")]

    def _hello(self, params: dict, session: Session) -> tuple[dict, Session]:
        if "protocol" not in params:
            return (
                error("invalid_params", "hello requires a protocol", missing=["protocol"]),
                session,
            )
        try:
            protocol = int(params["protocol"])
        except (TypeError, ValueError):
            return error("invalid_params", "hello protocol must be an integer"), session
        if protocol != self.contract.protocol:
            return (
                error(
                    "protocol_mismatch",
                    "client protocol is not supported",
                    supported=[self.contract.protocol],
                ),
                session,
            )
        client = str(params.get("client", "compat"))
        client_version = str(params.get("client_version", "0"))
        if not client or len(client) > 64 or len(client_version) > 64:
            return error("invalid_params", "invalid hello client identity"), session
        return (
            {
                "ok": True,
                "protocol": self.contract.protocol,
                "daemon_version": self.info.version,
                "pid": self.info.pid,
                "instance_id": self.info.instance_id,
                "started_at": self.info.started_at,
                "roles": list(self.info.roles),
            },
            Session(handshaken=True),
        )


class PipeServer:  # pragma: no cover - Windows-only integration surface
    """Blocking named-pipe server with a per-user DACL."""

    def __init__(self, plane: ControlPlane, *, pipe_name: str, on_stop: Callable[[], None]) -> None:
        if sys.platform != "win32":
            raise NotImplementedError("PipeServer is Windows-only")
        self.plane = plane
        self.pipe_name = pipe_name
        self.on_stop = on_stop
        self._handle = None
        self._kernel32, self._advapi32 = self._load_libraries()
        self._current_user_sid = self._sid()

    # --- win32 plumbing ------------------------------------------------------
    @staticmethod
    def _load_libraries():
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        ]
        kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ]
        # 缺 argtypes 时 64 位 HANDLE 会被截断，OpenProcessToken 直接失败。
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.LocalFree.restype = wintypes.HANDLE
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR),
        ]
        return kernel32, advapi32

    def _sid(self) -> str:
        import ctypes
        import ctypes.wintypes as wintypes

        token = wintypes.HANDLE()
        if not self._advapi32.OpenProcessToken(
            self._kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
        size = wintypes.DWORD(0)
        self._advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not self._advapi32.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation failed")
        sid_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        string_ptr = wintypes.LPWSTR()
        if not self._advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(string_ptr)):
            raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW failed")
        sid = string_ptr.value or ""
        self._kernel32.LocalFree(string_ptr)
        self._kernel32.CloseHandle(token)
        return sid

    def _security_attributes(self):
        import ctypes
        import ctypes.wintypes as wintypes

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL),
            ]

        sddl = f"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;{self._current_user_sid})"
        descriptor = ctypes.c_void_p()
        if not self._advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            wintypes.LPCWSTR(sddl), 1, ctypes.byref(descriptor), None
        ):
            raise OSError(ctypes.get_last_error(), "ConvertStringSecurityDescriptor failed")
        attributes = SECURITY_ATTRIBUTES()
        attributes.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        attributes.lpSecurityDescriptor = descriptor
        attributes.bInheritHandle = False
        return attributes, descriptor

    # --- server --------------------------------------------------------------
    def open(self) -> None:
        import ctypes

        attributes, descriptor = self._security_attributes()
        self._descriptor = descriptor
        handle = self._kernel32.CreateNamedPipeW(
            self.pipe_name,
            0x00000003,  # PIPE_ACCESS_DUPLEX
            0x00000004 | 0x00000002,  # PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE
            255,
            65536,
            65536,
            0,
            ctypes.byref(attributes),
        )
        if not handle or handle == -1:
            import ctypes

            raise OSError(ctypes.get_last_error(), "CreateNamedPipeW failed")
        self._handle = handle

    def serve_forever(self) -> None:
        import ctypes
        import ctypes.wintypes as wintypes

        buffer = ctypes.create_string_buffer(65536)
        while not self.plane.supervisor.stopping:
            if not self._kernel32.ConnectNamedPipe(self._handle, None):
                if ctypes.get_last_error() != 535:  # ERROR_PIPE_CONNECTED
                    continue
            session = Session()
            try:
                while True:
                    read = wintypes.DWORD(0)
                    ok = self._kernel32.ReadFile(
                        self._handle, buffer, ctypes.sizeof(buffer), ctypes.byref(read), None
                    )
                    if not ok or read.value == 0:
                        # A message larger than the buffer fails with
                        # ERROR_MORE_DATA. Tell the client instead of dropping
                        # the connection silently, then stop this session.
                        if ctypes.get_last_error() == 234:
                            payload = (
                                json.dumps(
                                    error(
                                        "frame_too_large",
                                        "control frame exceeds the pipe buffer",
                                        limit=MAX_FRAME_CHARS,
                                    ),
                                    ensure_ascii=False,
                                )
                                + "\n"
                            ).encode("utf-8")
                            written = wintypes.DWORD(0)
                            self._kernel32.WriteFile(
                                self._handle, payload, len(payload),
                                ctypes.byref(written), None,
                            )
                        break
                    line = buffer.raw[: read.value].decode("utf-8", "replace")
                    response, session = self.plane.dispatch(line, session)
                    if response.get("stopping"):
                        self.on_stop()
                    payload = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
                    written = wintypes.DWORD(0)
                    self._kernel32.WriteFile(
                        self._handle, payload, len(payload), ctypes.byref(written), None
                    )
            finally:
                self._kernel32.DisconnectNamedPipe(self._handle)

    def wake(self) -> None:
        import ctypes.wintypes as wintypes

        handle = self._kernel32.CreateFileW(
            self.pipe_name, 0x80000000 | 0x40000000, 0, None, 3, 0, None
        )
        if handle and handle != wintypes.HANDLE(-1).value:
            self._kernel32.CloseHandle(handle)

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def default_pipe_name() -> str:
    return os.environ.get("CAREERLENS_DAEMON_PIPE", r"\\.\pipe\careerlens-daemon")
