"""Process supervision for the user-level daemon.

Pure logic only: spawning, health probing, clock and sleeping are injected so
the restart/backoff/circuit behaviour can be tested deterministically without
starting real processes or waiting real seconds.

The daemon supervises roles (api, worker) and owns nothing else: it does not
create Runs, read business tables or generate answers.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol


class Process(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


@dataclass(frozen=True)
class Role:
    name: str
    env_flag: str


DEFAULT_ROLES = (
    Role("api", "CAREERLENS_SERVE"),
    Role("worker", "CAREERLENS_WORKER"),
)


@dataclass
class Child:
    role: Role
    process: Process | None = None
    restarts: int = 0
    restart_times: list[float] = field(default_factory=list)
    last_exit_code: int | None = None


@dataclass(frozen=True)
class SupervisorEvent:
    kind: str
    role: str
    detail: dict[str, object] = field(default_factory=dict)


class Supervisor:
    """Restarts crashed children with exponential backoff and a circuit breaker."""

    def __init__(
        self,
        roles: Iterable[Role] = DEFAULT_ROLES,
        *,
        spawn: Callable[[Role], Process],
        health: Callable[[], bool],
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        max_restarts: int = 6,
        restart_window: float = 60.0,
        backoff_base: float = 0.5,
        backoff_cap: float = 15.0,
    ) -> None:
        if max_restarts < 1:
            raise ValueError("max_restarts must be >= 1")
        self.children = {role.name: Child(role=role) for role in roles}
        self._spawn = spawn
        self._health = health
        self._now = now
        self._sleep = sleep
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.stopping = False

    # --- queries -------------------------------------------------------------
    def running(self, name: str) -> bool:
        child = self.children[name]
        return child.process is not None and child.process.poll() is None

    def now(self) -> float:
        return self._now()

    def healthy(self) -> bool:
        return self._health()

    def _live_pid(self, child: Child) -> int | None:
        if child.process is None or child.process.poll() is not None:
            return None
        return child.process.pid

    def status(self) -> dict[str, dict[str, object]]:
        return {
            name: {
                "pid": self._live_pid(child),
                "restarts": child.restarts,
                "running": self._live_pid(child) is not None,
            }
            for name, child in self.children.items()
        }

    # --- lifecycle -----------------------------------------------------------
    def start_all(self) -> list[SupervisorEvent]:
        events: list[SupervisorEvent] = []
        for name in self.children:
            events.append(self.start(name, reason="initial"))
        return events

    def start(self, name: str, *, reason: str) -> SupervisorEvent:
        child = self.children[name]
        child.process = self._spawn(child.role)
        return SupervisorEvent(
            "child.started",
            name,
            {"pid": child.process.pid, "reason": reason, "restarts": child.restarts},
        )

    def restart(self, name: str) -> SupervisorEvent | None:
        """Terminate one child so the supervisor restarts it on the next tick."""
        child = self.children[name]
        if child.process is None:
            return None
        if child.process.poll() is None:
            child.process.terminate()
        return SupervisorEvent("child.restart_requested", name)

    def stop(self, *, timeout: float = 8.0) -> list[SupervisorEvent]:
        self.stopping = True
        events: list[SupervisorEvent] = []
        for name, child in self.children.items():
            if child.process is None:
                continue
            if child.process.poll() is None:
                child.process.terminate()
            try:
                child.process.wait(timeout=timeout)
            except Exception:  # noqa: BLE001 - a hung child must not block shutdown
                child.process.kill()
            events.append(
                SupervisorEvent(
                    "child.stopped", name, {"pid": child.process.pid, "code": child.process.poll()}
                )
            )
            child.process = None
        return events

    # --- supervision ---------------------------------------------------------
    def _restart_allowed(self, child: Child) -> bool:
        now = self._now()
        child.restart_times = [t for t in child.restart_times if now - t < self.restart_window]
        return len(child.restart_times) < self.max_restarts

    def backoff(self, attempts: int) -> float:
        if attempts < 1:
            return 0.0
        return min(self.backoff_cap, self.backoff_base * (2 ** min(attempts - 1, 5)))

    def tick(self) -> list[SupervisorEvent]:
        events: list[SupervisorEvent] = []
        for name, child in self.children.items():
            process = child.process
            if process is None or process.poll() is None:
                continue
            code = process.returncode if hasattr(process, "returncode") else process.poll()
            child.process = None
            child.last_exit_code = code
            if self.stopping:
                events.append(SupervisorEvent("child.exited", name, {"code": code}))
                continue
            if not self._restart_allowed(child):
                events.append(
                    SupervisorEvent(
                        "child.circuit_open",
                        name,
                        {"code": code, "restarts_last_window": len(child.restart_times)},
                    )
                )
                continue
            child.restarts += 1
            child.restart_times.append(self._now())
            delay = self.backoff(child.restarts)
            events.append(
                SupervisorEvent(
                    "child.exited",
                    name,
                    {"code": code, "backoff": delay, "restarts": child.restarts},
                )
            )
            self._sleep(delay)
            if not self.stopping:
                events.append(self.start(name, reason=f"restart#{child.restarts}"))
        return events
