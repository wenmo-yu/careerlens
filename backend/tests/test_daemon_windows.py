"""Windows-only daemon surfaces: mutex lock, SID and the control pipe.

These checks are skipped everywhere else; the `daemon-windows` CI job is the
only place they run, and it is where a truncated HANDLE or a bad DACL shows up
before release.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import sys
import time

import pytest

from app.runtime.daemon.contract import load_contract
from app.runtime.daemon.control_ipc import ControlPlane, DaemonInfo, PipeServer, Session
from app.runtime.daemon.lifecycle import ProcessTree, SingleInstance
from app.runtime.daemon.supervisor import Role, Supervisor

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only daemon surface")


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.exit_code: int | None = None

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.exit_code = 0

    def kill(self) -> None:
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return 0


def build_plane(pipe_name: str, *, ready: bool = True) -> ControlPlane:
    supervisor = Supervisor(
        (Role("api", "FLAG_API"), Role("worker", "FLAG_WORKER")),
        spawn=lambda role: FakeProcess(900 + len(role.name)),
        health=lambda: True,
        now=lambda: 1000.0,
        sleep=lambda _seconds: None,
    )
    supervisor.start_all()
    info = DaemonInfo(
        version="0.2.0-m2",
        instance_id="windows-instance",
        started_at=990.0,
        pid=1234,
        roles=("api", "worker"),
    )
    return ControlPlane(load_contract(), supervisor, info, backend_url="http://127.0.0.1:8123/health/live",
                        ready=lambda: ready)


def test_mutex_is_exclusive_and_released():
    name = f"Local\\CareerLens.Test.{int(time.time() * 1000)}"
    first = SingleInstance(name=name)
    second = SingleInstance(name=name)

    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def test_process_tree_attaches_itself():
    tree = ProcessTree()
    assert tree.attach() is True
    tree.close()


def test_pipe_server_requires_hello(pipe_name: str):
    plane = build_plane(pipe_name)
    server = PipeServer(plane, pipe_name=pipe_name, on_stop=lambda: None)
    server.open()
    try:
        # 直接驱动分发，覆盖 DACL 建立之后的命令路径。
        response, session = plane.dispatch("status", Session())
        assert response["code"] == "not_ready"
        response, _ = plane.dispatch("hello 1", Session())
        assert response["ok"] is True
        assert response["protocol"] == 1
    finally:
        server.close()


def test_pipe_round_trip(pipe_name: str):
    plane = build_plane(pipe_name)
    server = PipeServer(plane, pipe_name=pipe_name, on_stop=lambda: None)
    server.open()
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 同一连接内先握手再查状态：新连接必须重新 hello。
        hello, status = _client_requests(pipe_name, ["hello 1", "status"])
        assert hello["ok"] is True
        assert status["children"]["api"]["running"] is True
    finally:
        plane.supervisor.stopping = True
        server.wake()
        server.close()


@pytest.fixture
def pipe_name() -> str:
    return rf"\\.\pipe\careerlens-test-{int(time.time() * 1000)}"


def _client_requests(pipe_name: str, commands: list[str]) -> list[dict]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    handle = kernel32.CreateFileW(pipe_name, 0x80000000 | 0x40000000, 0, None, 3, 0, None)
    assert handle and handle != wintypes.HANDLE(-1).value
    try:
        responses = []
        for command in commands:
            payload = command.encode("utf-8")
            written = wintypes.DWORD(0)
            assert kernel32.WriteFile(handle, payload, len(payload), ctypes.byref(written), None)
            buffer = ctypes.create_string_buffer(65536)
            read = wintypes.DWORD(0)
            assert kernel32.ReadFile(
                handle, buffer, ctypes.sizeof(buffer), ctypes.byref(read), None
            )
            responses.append(json.loads(buffer.raw[: read.value].decode("utf-8")))
        return responses
    finally:
        kernel32.CloseHandle(handle)
