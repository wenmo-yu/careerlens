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
from app.runtime.agent import store, tools
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


# --- M5 approval barrier and recovery through a restarted CLI ---------------

APPROVAL_CLI = '''\
import json
import os
import sys


def emit(kind, payload, run, seq):
    print(json.dumps({
        "v": 1, "type": "event", "kind": kind, "payload": payload,
        "local_seq": seq, "run_id": run["run_id"], "attempt": run["attempt"],
        "runtime_generation": run["runtime_generation"],
    }), flush=True)


def respond(request_id, result):
    print(json.dumps({"v": 1, "type": "response", "id": request_id,
                      "ok": True, "result": result}), flush=True)


print(json.dumps({"v": 1, "type": "event", "kind": "runtime.ready",
                  "payload": {"protocol": 1}}), flush=True)
generation = 0
for line in sys.stdin:
    frame = json.loads(line)
    if frame.get("type") != "request":
        continue
    request_id = frame["id"]
    method = frame["method"]
    params = frame.get("params") or {}
    if method == "runtime.bind":
        generation = int(params.get("runtime_generation", 0))
        respond(request_id, {"session_id": params.get("session_id")})
    elif method == "run.start":
        run = {
            "run_id": params["run_id"],
            "attempt": int(params.get("attempt", 1)),
            "runtime_generation": generation,
        }
        respond(request_id, {"accepted": True})
        pending = params.get("pending_tool")
        if pending:
            marker = os.environ.get("FAKE_CLI_MARKER", "")
            if marker:
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("executed")
            emit("tool.requested", {"invocation_ids": [pending["invocation_id"]]}, run, 1)
            emit("tool.completed", {
                "invocation_id": pending["invocation_id"],
                "status": "succeeded",
                "tool": pending["tool"],
                "args_digest": pending["args_digest"],
            }, run, 2)
            emit("run.settled", {
                "stop_reason": "completed",
                "message": {"text": "saved", "citations": []},
                "usage": {},
            }, run, 3)
        else:
            args = {"title": "t", "content": "c"}
            emit("tool.requested", {"invocation_ids": ["call-1"]}, run, 1)
            emit("approval.requested", {
                "invocation_id": "call-1",
                "tool": "save_career_note",
                "args_digest": DIGEST,
                "scope": "agent.artifact.write",
                "args": args,
                "tool_calls": [{"id": "call-1", "name": "save_career_note", "args": args}],
                "text": "draft",
                "turn": 0,
            }, run, 2)
    elif method == "runtime.shutdown":
        respond(request_id, {"stopping": True})
        sys.exit(0)
    else:
        respond(request_id, {"pong": True})
sys.exit(0)
'''


def approval_cli(tmp_path, digest):
    path = tmp_path / "approval_cli.py"
    path.write_text(APPROVAL_CLI.replace("DIGEST", repr(digest)), encoding="utf-8")
    return path


def approval_scheduler(factory, cli_path):
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
    return AgentScheduler(
        factory,
        config=config,
        cli_command=[sys.executable, "-u", str(cli_path), "--warm"],
        api_base="http://127.0.0.1:9",
    )


async def wait_for_approval_state(factory, run_id):
    async with factory() as session:
        run = await session.get(AgentRun, run_id)
        await session.refresh(run, ["payload"])
        assert run.status == "waiting_confirmation"
        return run.attempts, run.payload["pending_tool"]["approval_id"]


async def test_scheduler_recovers_approved_invocation_on_new_attempt(
    session_factory, tmp_path, monkeypatch
):
    args = {"title": "t", "content": "c"}
    digest = tools.digest_args(args)
    marker = tmp_path / "replayed.marker"
    monkeypatch.setenv("FAKE_CLI_MARKER", str(marker))
    _, run_id = await submit(session_factory, user="u1", text="write note")
    scheduler = approval_scheduler(session_factory, approval_cli(tmp_path, digest))
    try:
        await scheduler.tick()
        await scheduler.wait_idle()
        first_attempt, approval_id = await wait_for_approval_state(session_factory, run_id)
        async with session_factory.begin() as session:
            await store.decide_approval(
                session, user_id="u1", run_id=run_id, approve=True
            )
        async with session_factory.begin() as session:
            claim2 = await store.claim_agent_run(
                session, owner="scheduler-b", max_running=2
            )
        assert claim2 is not None and claim2.run_id == run_id
        assert claim2.attempt == first_attempt + 1
        assert claim2.payload["pending_tool"]["approval_id"] == approval_id
        result = await scheduler._drive(claim2)
        assert result.outcome == "committed"
        async with session_factory() as session:
            run = await session.get(AgentRun, run_id)
            assert run.status == "succeeded"
            kinds = list(
                await session.scalars(
                    select(RunEvent.event_type)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.seq)
                )
            )
            assert "run.settled" in kinds and "run.committed" in kinds
        assert marker.exists()  # 恢复的 invocation 恰好执行一次
    finally:
        await scheduler.shutdown()


async def test_scheduler_rejects_recovery_when_digest_changed(
    session_factory, tmp_path, monkeypatch
):
    args = {"title": "t", "content": "c"}
    digest = tools.digest_args(args)
    marker = tmp_path / "replayed.marker"
    monkeypatch.setenv("FAKE_CLI_MARKER", str(marker))
    _, run_id = await submit(session_factory, user="u1", text="write note")
    scheduler = approval_scheduler(session_factory, approval_cli(tmp_path, digest))
    try:
        await scheduler.tick()
        await scheduler.wait_idle()
        await wait_for_approval_state(session_factory, run_id)
        async with session_factory.begin() as session:
            await store.decide_approval(
                session, user_id="u1", run_id=run_id, approve=True
            )
        async with session_factory.begin() as session:
            run = await session.get(AgentRun, run_id)
            await session.refresh(run, ["payload"])
            payload = dict(run.payload)
            payload["pending_tool"] = dict(payload["pending_tool"])
            payload["pending_tool"]["args_digest"] = "0" * 64
            run.payload = payload
        async with session_factory.begin() as session:
            claim2 = await store.claim_agent_run(
                session, owner="scheduler-b", max_running=2
            )
        result = await scheduler._drive(claim2)
        assert result.outcome == "rejected" and result.error == "approval_mismatch"
        assert not marker.exists()  # digest 变化时绝不执行写工具
        async with session_factory() as session:
            run = await session.get(AgentRun, run_id)
            assert run.status == "failed" and run.error_code == "approval_mismatch"
    finally:
        await scheduler.shutdown()
