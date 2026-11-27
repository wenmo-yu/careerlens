import random

import pytest

from app.runtime.agent.pool import Pool, PoolError


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def build(**kwargs) -> tuple[Pool, FakeClock]:
    clock = FakeClock()
    pool = Pool(clock=clock, rng=random.Random(0), **kwargs)
    return pool, clock


def test_reserve_is_atomic_and_bound_shell_never_returns_to_pool():
    pool, _ = build(warm_target=1, total_cap=3)
    slot = pool.spawn("slot-1")
    pool.mark_warm(slot, pid=10)
    assert len(pool.warm()) == 1

    reserved = pool.reserve(session_id="s1", generation=2, run_id="r1")
    assert reserved is slot and reserved.state == "binding"
    assert pool.warm() == []
    # A second reservation cannot take the busy shell.
    assert pool.reserve(session_id="s2", generation=2, run_id="r2") is None

    pool.mark_ready(slot)
    pool.mark_running(slot)
    assert slot.bound is True
    pool.drain(slot, "run_finished")
    pool.terminate(slot)
    assert pool.warm() == []
    assert pool.reserve(session_id="s3", generation=2, run_id="r3") is None
    assert slot.session_id == "s1"  # kept for audit, never cleared for reuse


def test_total_process_cap_is_enforced():
    pool, _ = build(warm_target=2, total_cap=2)
    pool.spawn("a")
    pool.spawn("b")
    with pytest.raises(PoolError):
        pool.spawn("c")


def test_invalid_transitions_are_rejected():
    pool, _ = build()
    slot = pool.spawn("a")
    with pytest.raises(PoolError):
        pool.mark_ready(slot)
    pool.mark_warm(slot)
    with pytest.raises(PoolError):
        pool.mark_running(slot)
    pool.reserve(session_id="s", generation=1, run_id="r")
    pool.mark_ready(slot)
    pool.mark_running(slot)
    with pytest.raises(PoolError):
        pool.mark_warm(slot)


def test_warm_and_idle_bound_ttl_evict_but_running_does_not():
    pool, clock = build(warm_target=1, warm_ttl=10, idle_bound_ttl=5)
    warm = pool.spawn("warm")
    pool.mark_warm(warm)
    clock.now += 11
    evicted = pool.evict_idle()
    assert [slot.slot_id for slot in evicted] == ["warm"]
    assert warm.state == "draining"

    bound = pool.spawn("bound")
    pool.mark_warm(bound)
    pool.reserve(session_id="s1", generation=1, run_id="r1")
    pool.mark_ready(bound)
    clock.now += 6
    assert [slot.slot_id for slot in pool.evict_idle()] == ["bound"]

    running = pool.spawn("running")
    pool.mark_warm(running)
    pool.reserve(session_id="s2", generation=1, run_id="r2")
    pool.mark_ready(running)
    pool.mark_running(running)
    clock.now += 600
    assert pool.evict_idle() == []
    assert running.state == "running"


def test_fault_schedules_jittered_backoff_with_cap():
    pool, clock = build()
    slot = pool.spawn("a")
    pool.mark_warm(slot)
    delays = []
    for _ in range(6):
        pool.fault(slot, "lost")
        delays.append(pool.next_spawn_at - clock.now)
        clock.now += 100
        slot = pool.spawn(f"replacement-{clock.now}")
        pool.mark_warm(slot)
    assert 0.8 <= delays[0] <= 1.2
    assert 1.6 <= delays[1] <= 2.4
    assert 3.2 <= delays[2] <= 4.8
    assert 6.4 <= delays[3] <= 9.6
    assert 12.8 <= delays[4] <= 19.2
    assert 12.8 <= delays[5] <= 19.2


def test_snapshot_reports_pool_without_terminal_slots():
    pool, _ = build(warm_target=1)
    warm = pool.spawn("warm")
    pool.mark_warm(warm, pid=7)
    dead = pool.spawn("dead")
    pool.fault(dead, "spawn_failed")
    snapshot = pool.snapshot()
    assert snapshot["warm"] == 1
    assert snapshot["total_active"] == 1
    assert [slot["slot_id"] for slot in snapshot["slots"]] == ["warm"]
    assert snapshot["slots"][0]["pid"] == 7


def test_contract_pool_states_match_runtime():
    import json
    from pathlib import Path

    contract = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "agent-runtime-v1.json").read_text(
            encoding="utf-8"
        )
    )
    from app.runtime.agent import pool as pool_module

    runtime_states = {
        pool_module.SPAWNING,
        pool_module.WARM,
        pool_module.BINDING,
        pool_module.READY,
        pool_module.RUNNING,
        pool_module.WAITING,
        pool_module.DRAINING,
        pool_module.FAULTED,
        pool_module.TERMINATED,
    }
    assert set(contract["pool_states"]) == runtime_states
