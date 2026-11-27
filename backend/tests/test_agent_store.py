import hashlib
import json

import pytest
from sqlalchemy import select

from app.models.agent import AgentApproval
from app.models.run import AgentRun, RunEvent
from app.runtime.agent import store


def booking_key(user: str, session: str, text: str) -> str:
    return hashlib.sha256(f"{user}|{session}|{text}".encode()).hexdigest()[:32]


async def new_turn(factory, *, user="u1", text="find Docker evidence"):
    async with factory.begin() as session:
        record = await store.create_session(session, user_id=user, title="t")
        run, created = await store.submit_turn(
            session,
            user_id=user,
            session_id=record.id,
            text=text,
            token_id=None,
            request_key=booking_key(user, record.id, text),
        )
        return record.id, run.id, created


async def claim(factory, *, owner="worker-a", max_running=2):
    async with factory.begin() as session:
        return await store.claim_agent_run(session, owner=owner, max_running=max_running)


async def bind_and_ack(factory, claim_row):
    async with factory.begin() as session:
        generation = await store.bind_generation(session, claim=claim_row)
    async with factory.begin() as session:
        await store.acknowledge(
            session, claim=claim_row, generation=generation, slot_id="slot-1"
        )
    return generation


async def test_submit_acks_and_commits_are_separate(session_factory):
    session_id, run_id, created = await new_turn(session_factory)
    assert created is True

    row = await claim(session_factory)
    assert row is not None and row.run_id == run_id
    generation = await bind_and_ack(session_factory, row)
    assert generation == 2

    async with session_factory.begin() as session:
        await store.append_event(
            session,
            claim=row,
            generation=generation,
            kind="message.delta",
            data={"text": "partial"},
        )

    async with session_factory.begin() as session:
        run = await store.settle(
            session,
            claim=row,
            generation=generation,
            stop_reason="completed",
            text="final answer",
            citations=[{"evidence_id": "e1"}],
            usage={"input_tokens": 1, "output_tokens": 2},
        )
        assert run.status == "succeeded"

    async with session_factory() as session:
        events = list(
            await session.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        )
        kinds = [event.event_type for event in events]
        assert kinds[:3] == ["run.queued", "run.started", "run.acknowledged"]
        assert kinds[-3:] == ["message.delta", "run.settled", "run.committed"]
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        messages = await store.read_messages(
            session, user_id="u1", session_id=session_id
        )
        assert [(m.role, m.content) for m in messages] == [
            ("user", "find Docker evidence"),
            ("assistant", "final answer"),
        ]
        assert messages[1].citations == [{"evidence_id": "e1"}]


async def test_stale_claim_and_wrong_generation_are_rejected(session_factory):
    _, run_id, _ = await new_turn(session_factory)
    row = await claim(session_factory)
    generation = await bind_and_ack(session_factory, row)
    async with session_factory.begin() as session:
        await store.settle(
            session,
            claim=row,
            generation=generation,
            stop_reason="completed",
            text="done",
        )

    with pytest.raises(store.StaleClaim):
        async with session_factory.begin() as session:
            await store.append_event(
                session, claim=row, generation=generation, kind="message.delta", data={"text": "x"}
            )

    _, run_id2, _ = await new_turn(session_factory, user="u2", text="second")
    row2 = await claim(session_factory)
    generation2 = await bind_and_ack(session_factory, row2)
    with pytest.raises(store.StaleClaim):
        async with session_factory.begin() as session:
            await store.append_event(
                session,
                claim=row2,
                generation=generation2 + 1,
                kind="message.delta",
                data={"text": "x"},
            )
    async with session_factory() as session:
        run = await session.get(AgentRun, run_id2)
        assert run.status == "running"


async def test_idempotent_turn_does_not_duplicate_messages(session_factory):
    async with session_factory.begin() as session:
        record = await store.create_session(session, user_id="u1")
        session_id = record.id
        key = booking_key("u1", session_id, "same text")
        first, created = await store.submit_turn(
            session,
            user_id="u1",
            session_id=session_id,
            text="same text",
            token_id=None,
            request_key=key,
        )
        second, created_again = await store.submit_turn(
            session,
            user_id="u1",
            session_id=session_id,
            text="same text",
            token_id=None,
            request_key=key,
        )
        assert created is True and created_again is False
        assert first.id == second.id
    async with session_factory() as session:
        messages = await store.read_messages(session, user_id="u1", session_id=session_id)
        assert len(messages) == 1


async def test_denied_approval_cancels_and_approved_requeues(session_factory):
    _, run_id, _ = await new_turn(session_factory)
    row = await claim(session_factory)
    generation = await bind_and_ack(session_factory, row)
    async with session_factory.begin() as session:
        approval = await store.wait_for_approval(
            session,
            claim=row,
            generation=generation,
            invocation_id="call-1",
            tool="overwrite_profile",
            args_digest="d" * 64,
        )
        assert approval.status == "pending"

    async with session_factory.begin() as session:
        pending = await store.pending_approvals(session, user_id="u1")
        assert [item.id for item in pending] == [approval.id]
        run = await store.decide_approval(
            session, user_id="u1", run_id=run_id, approve=False
        )
        assert run.status == "cancelled" and run.error_code == "rejected"

    async with session_factory() as session:
        stored = await session.scalar(
            select(AgentApproval).where(AgentApproval.run_id == run_id)
        )
        assert stored.status == "denied"

    _, run_id2, _ = await new_turn(session_factory, user="u2", text="needs approval")
    row2 = await claim(session_factory)
    generation2 = await bind_and_ack(session_factory, row2)
    async with session_factory.begin() as session:
        await store.wait_for_approval(
            session,
            claim=row2,
            generation=generation2,
            invocation_id="call-2",
            tool="overwrite_profile",
            args_digest="e" * 64,
        )
    async with session_factory.begin() as session:
        run = await store.decide_approval(
            session, user_id="u2", run_id=run_id2, approve=True
        )
        assert run.status == "queued" and run.confirmation == "approved"
    retry = await claim(session_factory)
    assert retry is not None and retry.run_id == run_id2 and retry.attempt == 2


async def test_concurrent_sessions_are_admitted_and_one_per_session(session_factory):
    await new_turn(session_factory, user="u1", text="one")
    await new_turn(session_factory, user="u2", text="two")
    first = await claim(session_factory)
    second = await claim(session_factory)
    assert first is not None and second is not None
    assert first.run_id != second.run_id
    third = await claim(session_factory)
    assert third is None  # admission limit is two
    async with session_factory() as session:
        running = list(
            await session.scalars(
                select(AgentRun).where(
                    AgentRun.executor_kind == "agent", AgentRun.status == "running"
                )
            )
        )
        assert len(running) == 2


async def test_events_are_json_serialisable_no_defaults(session_factory):
    _, run_id, _ = await new_turn(session_factory)
    row = await claim(session_factory)
    generation = await bind_and_ack(session_factory, row)
    async with session_factory.begin() as session:
        seq = await store.append_event(
            session,
            claim=row,
            generation=generation,
            kind="tool.completed",
            data={"invocation_id": "c1", "status": "succeeded"},
        )
    async with session_factory() as session:
        event = await session.scalar(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq == seq)
        )
        json.dumps(event.data)
        assert event.data["attempt"] == row.attempt
        assert event.data["runtime_generation"] == generation


def test_contract_event_kinds_match_runtime():
    import json
    from pathlib import Path

    contract = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "agent-runtime-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert {item["kind"] for item in contract["run_events"]} == set(store.RUN_EVENT_KINDS)
