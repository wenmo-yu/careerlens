"""Control plane dispatch: handshake, error codes and command results."""

from __future__ import annotations

from dataclasses import dataclass

from app.runtime.daemon.contract import load_contract
from app.runtime.daemon.control_ipc import ControlPlane, DaemonInfo, Session
from app.runtime.daemon.supervisor import Role, Supervisor


@dataclass
class FakeProcess:
    pid: int
    exit_code: int | None = None
    terminated: bool = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        self.exit_code = 0

    def kill(self) -> None:
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return 0


def build(*, ready: bool = True, healthy: bool = True) -> ControlPlane:
    processes: list[FakeProcess] = []

    def spawn(role: Role) -> FakeProcess:
        process = FakeProcess(pid=200 + len(processes))
        processes.append(process)
        return process

    supervisor = Supervisor(
        (Role("api", "FLAG_API"), Role("worker", "FLAG_WORKER")),
        spawn=spawn,
        health=lambda: healthy,
        now=lambda: 1000.0,
        sleep=lambda _seconds: None,
    )
    supervisor.start_all()
    info = DaemonInfo(
        version="0.2.0-m2",
        instance_id="instance-1",
        started_at=990.0,
        pid=4321,
        roles=("api", "worker"),
    )
    return ControlPlane(
        load_contract(), supervisor, info, backend_url="http://127.0.0.1:8123/health/live",
        ready=lambda: ready,
    )


def test_hello_returns_protocol_and_instance():
    plane = build()
    response, session = plane.dispatch("hello 1", Session())

    assert response["ok"] is True
    assert response["protocol"] == 1
    assert response["instance_id"] == "instance-1"
    assert response["pid"] == 4321
    assert response["roles"] == ["api", "worker"]
    assert session.handshaken is True


def test_command_without_hello_is_not_ready():
    plane = build()
    response, session = plane.dispatch("status", Session())

    assert response["code"] == "not_ready"
    assert session.handshaken is False


def test_unsupported_protocol_is_rejected_with_supported_list():
    plane = build()
    response, session = plane.dispatch("hello 2", Session())

    assert response["ok"] is False
    assert response["code"] == "protocol_mismatch"
    assert response["supported"] == [1]
    assert session.handshaken is False


def test_failed_rehello_does_not_drop_an_established_session():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, session = plane.dispatch("hello 9", session)

    assert response["code"] == "protocol_mismatch"
    assert session.handshaken is True
    followup, _ = plane.dispatch("ping", session)
    assert followup == {"ok": True, "pong": True}


def test_hello_without_protocol_is_invalid():
    plane = build()
    response, _ = plane.dispatch("hello", Session())
    assert response["code"] == "invalid_params"
    assert response["missing"] == ["protocol"]


def test_unknown_command_after_handshake():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("fly", session)
    assert response["code"] == "unknown_command"


def test_status_reports_daemon_backend_and_children():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("status", session)

    assert response["ok"] is True
    assert response["daemon"]["pid"] == 4321
    assert response["daemon"]["version"] == "0.2.0-m2"
    assert response["backend"]["healthy"] is True
    assert response["backend"]["url"].endswith("/health/live")
    assert set(response["children"]) == {"api", "worker"}
    assert response["children"]["api"]["running"] is True


def test_status_waits_for_readiness():
    plane = build(ready=False)
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("status", session)
    assert response["code"] == "not_ready"


def test_ping_works_before_ready():
    plane = build(ready=False)
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("ping", session)
    assert response == {"ok": True, "pong": True}


def test_restart_rejects_unknown_role():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("restart database", session)
    assert response["code"] == "unknown_role"


def test_restart_requires_a_role_argument():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("restart", session)
    assert response["code"] == "invalid_params"
    assert response["missing"] == ["role"]


def test_restart_terminates_the_requested_child():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("restart worker", session)

    assert response == {"ok": True, "restarting": "worker"}
    assert plane.supervisor.children["worker"].process.terminated is True


def test_stop_returns_stopping_flag():
    plane = build()
    _, session = plane.dispatch("hello 1", Session())
    response, _ = plane.dispatch("stop", session)
    assert response == {"ok": True, "stopping": True}


def test_empty_command_is_invalid():
    plane = build()
    response, _ = plane.dispatch("   ", Session())
    assert response["code"] == "invalid_params"
