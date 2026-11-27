"""Supervisor behaviour: restart, backoff, circuit breaker, shutdown."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.runtime.daemon.supervisor import Role, Supervisor


@dataclass
class FakeProcess:
    pid: int
    exit_code: int | None = None
    terminated: bool = False
    killed: bool = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True
        if self.exit_code is None:
            self.exit_code = 0

    def kill(self) -> None:
        self.killed = True
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.exit_code or 0

    @property
    def returncode(self) -> int | None:
        return self.exit_code


class Harness:
    def __init__(self, *, healthy: bool = True, max_restarts: int = 6) -> None:
        self.processes: list[FakeProcess] = []
        self.sleeps: list[float] = []
        self.clock = 1000.0
        self.healthy = healthy
        self.supervisor = Supervisor(
            (Role("api", "FLAG_API"), Role("worker", "FLAG_WORKER")),
            spawn=self._spawn,
            health=lambda: self.healthy,
            now=lambda: self.clock,
            sleep=self.sleeps.append,
            max_restarts=max_restarts,
        )

    def _spawn(self, role: Role) -> FakeProcess:
        process = FakeProcess(pid=100 + len(self.processes))
        self.processes.append(process)
        return process

    def crash(self, pid: int, code: int = 1) -> None:
        for process in self.processes:
            if process.pid == pid:
                process.exit_code = code


def test_start_all_spawns_each_role_once():
    harness = Harness()
    events = harness.supervisor.start_all()
    assert [event.kind for event in events] == ["child.started", "child.started"]
    assert len(harness.processes) == 2
    assert harness.supervisor.running("api") and harness.supervisor.running("worker")


def test_crashed_child_restarts_with_backoff():
    harness = Harness()
    harness.supervisor.start_all()
    api_pid = harness.supervisor.children["api"].process.pid
    harness.crash(api_pid)

    events = harness.supervisor.tick()

    assert [event.kind for event in events] == ["child.exited", "child.started"]
    assert harness.sleeps == [0.5]
    child = harness.supervisor.children["api"]
    assert child.restarts == 1
    assert child.process is not None and child.process.pid != api_pid
    assert harness.supervisor.running("api")


def test_backoff_grows_and_is_capped():
    harness = Harness()
    assert harness.supervisor.backoff(1) == 0.5
    assert harness.supervisor.backoff(2) == 1.0
    assert harness.supervisor.backoff(3) == 2.0
    assert harness.supervisor.backoff(9) == 15.0


def test_circuit_opens_after_max_restarts_in_window():
    harness = Harness(max_restarts=2)
    harness.supervisor.start_all()
    child = harness.supervisor.children["api"]

    for _ in range(2):
        harness.crash(child.process.pid)
        harness.clock += 1
        harness.supervisor.tick()

    harness.crash(child.process.pid)
    harness.clock += 1
    events = harness.supervisor.tick()

    assert [event.kind for event in events] == ["child.circuit_open"]
    assert child.restarts == 2


def test_restart_window_expires_old_restarts():
    harness = Harness(max_restarts=2)
    harness.supervisor.start_all()
    child = harness.supervisor.children["api"]

    for _ in range(2):
        harness.crash(child.process.pid)
        harness.clock += 1
        harness.supervisor.tick()

    harness.clock += 120  # 超出 60 秒窗口
    harness.crash(child.process.pid)
    events = harness.supervisor.tick()

    assert [event.kind for event in events] == ["child.exited", "child.started"]


def test_restart_terminates_only_the_requested_role():
    harness = Harness()
    harness.supervisor.start_all()
    event = harness.supervisor.restart("worker")

    assert event is not None and event.role == "worker"
    assert harness.supervisor.children["worker"].process.terminated is True
    assert harness.supervisor.children["api"].process.terminated is False


def test_status_reports_pid_and_running_state():
    harness = Harness()
    harness.supervisor.start_all()
    status = harness.supervisor.status()

    assert set(status) == {"api", "worker"}
    assert status["api"]["running"] is True
    assert isinstance(status["api"]["pid"], int)
    assert status["api"]["restarts"] == 0


def test_stop_terminates_every_child_and_marks_stopping():
    harness = Harness()
    harness.supervisor.start_all()
    events = harness.supervisor.stop()

    assert harness.supervisor.stopping is True
    assert [event.kind for event in events] == ["child.stopped", "child.stopped"]
    assert all(process.terminated for process in harness.processes)
    assert harness.supervisor.status()["api"]["pid"] is None


def test_tick_does_not_restart_while_stopping():
    harness = Harness()
    harness.supervisor.start_all()
    harness.supervisor.stopping = True
    harness.crash(harness.supervisor.children["api"].process.pid)

    events = harness.supervisor.tick()

    assert [event.kind for event in events] == ["child.exited"]
    assert harness.supervisor.children["api"].process is None


def test_invalid_max_restarts_is_rejected():
    with pytest.raises(ValueError):
        Supervisor(spawn=lambda role: FakeProcess(1), health=lambda: True, max_restarts=0)
