"""Runtime pool state machine (M4).

Rules taken from the V4 contract:

* a warm shell holds no user history and cannot be reused across sessions;
* ``reserve`` is atomic and a bound shell is never returned to the pool;
* a lost shell becomes ``faulted`` and is replaced with jittered backoff;
* warm TTL and idle-bound TTL evict without touching an active run.

The pool is pure Python. Process spawning, DB writes and I/O live in the
scheduler so this state machine can be tested deterministically.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

WARM = "warm"
SPAWNING = "spawning"
BINDING = "binding"
READY = "ready"
RUNNING = "running"
WAITING = "waiting"
DRAINING = "draining"
FAULTED = "faulted"
TERMINATED = "terminated"

BACKOFF_STEPS = (1.0, 2.0, 4.0, 8.0, 16.0)


@dataclass
class Slot:
    slot_id: str
    state: str = SPAWNING
    generation: int = 0
    session_id: str | None = None
    run_id: str | None = None
    pid: int | None = None
    fencing_token: int = 0
    state_changed_at: float = 0.0
    restarts: int = 0
    fault_reason: str | None = None
    process: object | None = None
    busy: bool = False
    diagnostics: dict = field(default_factory=dict)

    @property
    def bound(self) -> bool:
        return bool(self.session_id)

    @property
    def terminal(self) -> bool:
        return self.state in (FAULTED, TERMINATED)


class PoolError(RuntimeError):
    pass


class Pool:
    def __init__(
        self,
        *,
        warm_target: int = 1,
        warm_max: int = 2,
        total_cap: int = 6,
        warm_ttl: float = 600.0,
        idle_bound_ttl: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ):
        self.warm_target = warm_target
        self.warm_max = warm_max
        self.total_cap = total_cap
        self.warm_ttl = warm_ttl
        self.idle_bound_ttl = idle_bound_ttl
        self._clock = clock
        self._rng = rng or random.Random(0)
        self.slots: list[Slot] = []
        self.next_spawn_at = 0.0
        self.pool_faults = 0

    # ---- queries -----------------------------------------------------
    def warm(self) -> list[Slot]:
        return [slot for slot in self.slots if slot.state == WARM]

    def active(self) -> list[Slot]:
        return [slot for slot in self.slots if not slot.terminal]

    def bound_slots(self) -> list[Slot]:
        return [slot for slot in self.slots if slot.bound and not slot.terminal]

    def running(self) -> list[Slot]:
        return [slot for slot in self.slots if slot.state in (READY, RUNNING, WAITING, BINDING)]

    def can_spawn(self) -> bool:
        return len(self.active()) < self.total_cap

    def warm_deficit(self) -> int:
        return max(0, self.warm_target - len(self.warm()))

    # ---- transitions -------------------------------------------------
    def spawn(self, slot_id: str) -> Slot:
        if not self.can_spawn():
            raise PoolError("CLI total process cap reached")
        slot = Slot(slot_id=slot_id, state=SPAWNING, state_changed_at=self._clock())
        self.slots.append(slot)
        return slot

    def mark_warm(self, slot: Slot, *, pid: int | None = None) -> None:
        if slot.state != SPAWNING:
            raise PoolError(f"cannot warm a {slot.state} slot")
        slot.state = WARM
        slot.pid = pid
        slot.state_changed_at = self._clock()
        slot.busy = False

    def reserve(self, *, session_id: str, generation: int, run_id: str) -> Slot | None:
        """Atomically take one warm shell for a session. Never reuses a bound shell."""

        candidates = sorted(self.warm(), key=lambda slot: slot.state_changed_at)
        if not candidates:
            return None
        slot = candidates[0]
        slot.state = BINDING
        slot.session_id = session_id
        slot.generation = generation
        slot.run_id = run_id
        slot.state_changed_at = self._clock()
        slot.busy = True
        return slot

    def mark_ready(self, slot: Slot) -> None:
        self._expect(slot, (BINDING, WAITING))
        slot.state = READY
        slot.state_changed_at = self._clock()

    def mark_running(self, slot: Slot) -> None:
        self._expect(slot, (READY,))
        slot.state = RUNNING
        slot.state_changed_at = self._clock()
        slot.busy = True

    def mark_waiting(self, slot: Slot) -> None:
        self._expect(slot, (RUNNING,))
        slot.state = WAITING
        slot.state_changed_at = self._clock()
        slot.busy = True

    def drain(self, slot: Slot, reason: str) -> None:
        if slot.terminal:
            return
        slot.state = DRAINING
        slot.fault_reason = reason
        slot.state_changed_at = self._clock()
        slot.busy = True

    def terminate(self, slot: Slot) -> None:
        if slot.state == TERMINATED:
            return
        slot.state = TERMINATED
        slot.state_changed_at = self._clock()
        slot.busy = False
        slot.process = None
        slot.pid = None

    def fault(self, slot: Slot, reason: str) -> None:
        """Shell loss: keep the binding for audit, refuse reuse, schedule refill."""

        if slot.state == TERMINATED:
            return
        slot.state = FAULTED
        slot.fault_reason = reason
        slot.state_changed_at = self._clock()
        slot.busy = False
        slot.process = None
        slot.pid = None
        self.pool_faults += 1
        self.next_spawn_at = self._clock() + self.backoff(self.pool_faults)

    # ---- maintenance -------------------------------------------------
    def backoff(self, failures: int) -> float:
        base = BACKOFF_STEPS[min(max(failures, 1) - 1, len(BACKOFF_STEPS) - 1)]
        return base * (0.8 + 0.4 * self._rng.random())

    def evict_idle(self) -> list[Slot]:
        now = self._clock()
        evicted: list[Slot] = []
        for slot in list(self.slots):
            if slot.state == WARM and now - slot.state_changed_at >= self.warm_ttl:
                self.drain(slot, "warm_ttl")
                evicted.append(slot)
            elif (
                slot.state in (READY, WAITING)
                and slot.bound
                and now - slot.state_changed_at >= self.idle_bound_ttl
            ):
                self.drain(slot, "idle_bound_ttl")
                evicted.append(slot)
        return evicted

    def snapshot(self) -> dict:
        return {
            "warm_target": self.warm_target,
            "warm_max": self.warm_max,
            "total_cap": self.total_cap,
            "total_active": len(self.active()),
            "warm": len(self.warm()),
            "bound": len(self.bound_slots()),
            "running": len(self.running()),
            "pool_faults": self.pool_faults,
            "slots": [
                {
                    "slot_id": slot.slot_id,
                    "state": slot.state,
                    "session_id": slot.session_id,
                    "run_id": slot.run_id,
                    "pid": slot.pid,
                    "generation": slot.generation,
                    "restarts": slot.restarts,
                    "fault_reason": slot.fault_reason,
                }
                for slot in self.slots
                if not slot.terminal
            ],
        }

    def _expect(self, slot: Slot, states: tuple[str, ...]) -> None:
        if slot.state not in states:
            raise PoolError(f"invalid transition {slot.state} -> requires {states}")
