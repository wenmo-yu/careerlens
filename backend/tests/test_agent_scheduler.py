import asyncio
import hashlib
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.agent import AgentMessage, AgentRuntimeSlot
from app.models.run import TERMINAL, AgentRun, RunEvent
from app.runtime.agent import scheduler as scheduler_module
from app.runtime.agent import store
from app.runtime.agent.scheduler import AgentScheduler, SchedulerConfig

FAKE_CLI = Path(__file__).with_name("fake_agent_cli.py")


def key(user: str, session: str, text: str) -> str:
    return hashlib.sha256(f"{user}|{session}|{text}".encode()).hexdigest()[:32]


async def submit(factory, *, user: str, text: str) -> tuple[str, str]:
    async with factory.begin() as session:
        record = await store.create_session(session, user_id=user, title=text)
        run, _ = await store.submit_turn(
            session,
            user_id=user,
            session_id=record.id,
            text=text,
            token_id=None,
            request_key=key(user, record.id, text),
        )
        return record.id, run.id


def make_scheduler(factory, **overrides) -> AgentScheduler:
    config = SchedulerConfig(
        max_running=2,
        warm_target=1,
        warm_max=2,
        total_cap=4,
        warm_ttl=600,
        idle_bound_ttl=300,
        turn_timeout=15,
        bind_timeout=15,
        poll_seconds=0.01,
    )
    for name, value in overrides.items():
        setattr(config, name, value)
    return AgentScheduler(
        factory,
        config=config,
        cli_command=[sys.executable, "-u", str(FAKE_CLI), "--warm"],
        api_base="http://127.0.0.1:9",
    )


async def drive_until_terminal(scheduler, factory, run_ids, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await scheduler.tick()
        await scheduler.wait_idle()
        async with factory() as session:
            rows = [await session.get(AgentRun, run_id) for run_id in run_ids]
        if all(row is not None and row.status in TERMINAL for row in rows):
            return rows
        await asyncio.sleep(0.02)
    raise AssertionError("runs did not settle in time")


async def test_two_concurrent_sessions_commit_and_release_shells(session_factory):
    _, run_a = await submit(session_factory, user="u1", text="alpha")
    _, run_b = await submit(session_factory, user="u2", text="beta")
    scheduler = make_scheduler(session_factory)
    try:
        rows = await drive_until_terminal(scheduler, session_factory, [run_a, run_b])
        assert [row.status for row in rows] == ["succeeded", "succeeded"]
        async with session_factory() as session:
            for run_id in (run_a, run_b):
                kinds = list(
                    await session.scalars(
                        select(RunEvent.event_type)
                        .where(RunEvent.run_id == run_id)
                        .order_by(RunEvent.seq)
                    )
                )
                assert kinds[0] == "run.queued"
                assert kinds[1] == "run.started"
                assert "run.acknowledged" in kinds
                assert kinds[-2:] == ["run.settled", "run.committed"]
                messages = list(
                    await session.scalars(
                        select(AgentMessage).where(AgentMessage.run_id == run_id)
                    )
                )
                assert messages[-1].content == "hello world"
                assert messages[-1].citations == [{"evidence_id": "e1"}]
            slots = list(await session.scalars(select(AgentRuntimeSlot)))
            assert slots
            assert all(slot.state in ("terminated", "faulted") for slot in slots)
        assert scheduler.pool.bound_slots() == []
    finally:
        await scheduler.shutdown()


async def test_crash_is_retried_and_backoff_refills_pool(session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "crash_first")
    monkeypatch.setenv("FAKE_CLI_MARKER", str(tmp_path / "crashed.marker"))
    _, run_id = await submit(session_factory, user="u1", text="crash once")
    scheduler = make_scheduler(session_factory)
    try:
        rows = await drive_until_terminal(scheduler, session_factory, [run_id])
        assert rows[0].status == "succeeded"
        assert rows[0].attempts == 2
        async with session_factory() as session:
            kinds = list(
                await session.scalars(
                    select(RunEvent.event_type)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.seq)
                )
            )
            assert "run.interrupted" in kinds
        assert scheduler.pool.pool_faults >= 1
        assert scheduler.pool.backoff(1) >= 0.8
    finally:
        await scheduler.shutdown()


async def test_stale_generation_never_commits_and_exhausts_attempts(
    session_factory, monkeypatch
):
    monkeypatch.setenv("FAKE_CLI_MODE", "stale_generation")
    _, run_id = await submit(session_factory, user="u1", text="stale")
    scheduler = make_scheduler(session_factory)
    try:
        rows = await drive_until_terminal(scheduler, session_factory, [run_id], timeout=40)
        row = rows[0]
        assert row.status == "failed"
        assert row.error_code == "stale_generation"
        assert row.attempts == row.max_attempts
        async with session_factory() as session:
            kinds = list(
                await session.scalars(
                    select(RunEvent.event_type)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.seq)
                )
            )
            assert "run.committed" not in kinds
            assert kinds.count("run.interrupted") == row.max_attempts - 1
    finally:
        await scheduler.shutdown()


async def test_startup_faults_slots_left_by_a_previous_scheduler(session_factory):
    async with session_factory.begin() as session:
        session.add(
            AgentRuntimeSlot(
                slot_id="orphan",
                state="running",
                generation=3,
                session_id="s1",
                run_id="r1",
                pid=4242,
            )
        )
    scheduler = make_scheduler(session_factory)
    await scheduler.startup()
    async with session_factory() as session:
        slot = await session.get(AgentRuntimeSlot, "orphan")
        assert slot.state == "faulted"
        assert slot.pid is None
    await scheduler.shutdown()


async def test_shutdown_kills_spawned_processes(session_factory):
    scheduler = make_scheduler(session_factory)
    await scheduler.startup()
    await scheduler.tick()
    assert scheduler.processes
    await scheduler.shutdown()
    assert scheduler.processes == {}


async def test_six_queued_runs_never_exceed_admission_or_process_cap(session_factory):
    run_ids = []
    for index in range(6):
        _, run_id = await submit(session_factory, user=f"stress-{index}", text=f"job {index}")
        run_ids.append(run_id)
    scheduler = make_scheduler(session_factory)
    try:
        rows = await drive_until_terminal(scheduler, session_factory, run_ids, timeout=60)
        assert all(row.status == "succeeded" for row in rows)
        assert scheduler.pool.active() == []
        assert scheduler.pool.total_cap == 4
        async with session_factory() as session:
            slots = list(await session.scalars(select(AgentRuntimeSlot)))
            assert all(slot.state == "terminated" for slot in slots)
    finally:
        await scheduler.shutdown()


async def test_long_task_times_out_and_exhausts_retries(session_factory, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "slow")
    _, run_id = await submit(session_factory, user="u1", text="long")
    scheduler = make_scheduler(session_factory, turn_timeout=0.5)
    try:
        rows = await drive_until_terminal(scheduler, session_factory, [run_id], timeout=45)
        assert rows[0].status == "failed"
        assert rows[0].error_code == "cli_timeout"
        assert rows[0].attempts == rows[0].max_attempts
    finally:
        await scheduler.shutdown()


def test_scheduler_entry_requires_the_enable_flag(monkeypatch):
    class Disabled:
        agent_runtime_enabled = False

    monkeypatch.setattr(scheduler_module, "get_settings", lambda: Disabled())
    with pytest.raises(SystemExit):
        scheduler_module.main()
