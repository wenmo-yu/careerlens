"""Lifecycle helpers that stay platform-neutral: locks, spawner, health, entry."""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.runtime.daemon import lifecycle
from app.runtime.daemon.lifecycle import (
    DaemonConfig,
    ProcessTree,
    SingleInstance,
    build_spawner,
    probe_health,
    run_daemon,
    wait_ready,
)
from app.runtime.daemon.supervisor import Role


def test_single_instance_is_exclusive_until_released(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle.tempfile, "gettempdir", lambda: str(tmp_path))
    first = SingleInstance(name="careerlens-test-lock")
    second = SingleInstance(name="careerlens-test-lock")

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()
    assert second.acquire() is True
    second.release()


def test_release_without_acquire_is_safe():
    lock = SingleInstance(name="careerlens-test-unused")
    lock.release()
    assert lock._handle is None


def test_process_tree_is_a_noop_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    tree = ProcessTree()
    assert tree.attach() is False
    tree.close()


def test_build_spawner_passes_role_flag_and_base_env(monkeypatch):
    captured: dict[str, object] = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["env"] = kwargs["env"]

    monkeypatch.setattr(lifecycle.subprocess, "Popen", FakePopen)
    spawner = build_spawner(DaemonConfig(api_exe="C:/app/probe.exe", base_env={"A": "1"}))
    spawner(Role("api", "CAREERLENS_SERVE"))

    assert captured["args"] == ["C:/app/probe.exe"]
    env = captured["env"]
    assert env["CAREERLENS_SERVE"] == "1"
    assert env["A"] == "1"


def test_probe_health_returns_true_on_200(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_a, **_k: Response())
    assert probe_health("http://127.0.0.1:1/health/live") is True


def test_probe_health_returns_false_on_error(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("refused")

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", boom)
    assert probe_health("http://127.0.0.1:1/health/live") is False


def test_wait_ready_returns_immediately_when_healthy():
    assert wait_ready(lambda: True, timeout=5, sleep=lambda _s: None) is True


def test_wait_ready_times_out():
    clock = {"value": 0.0}

    def monotonic() -> float:
        clock["value"] += 1.0
        return clock["value"]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lifecycle.time, "monotonic", monotonic)
    try:
        assert wait_ready(lambda: False, timeout=2, sleep=lambda _s: None) is False
    finally:
        monkeypatch.undo()


def test_run_daemon_exits_three_when_instance_exists(monkeypatch, capsys):
    monkeypatch.setattr(SingleInstance, "acquire", lambda self: False)
    code = run_daemon(DaemonConfig(api_exe="unused"))
    assert code == 3
    assert "DAEMON_ALREADY_RUNNING" in capsys.readouterr().out


def test_spawn_uses_new_session_outside_windows(monkeypatch):
    captured: dict[str, object] = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    config = DaemonConfig(api_exe="app.exe")
    spawner = build_spawner(config)
    spawner(Role("worker", "CAREERLENS_WORKER"))
    expected = sys.platform != "win32"
    assert captured["start_new_session"] is expected
