"""HY4-E: parallel-safe runtime primitives and read-only specialists."""

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.database import Base
from app.models.run import AgentRun, RunEvent
from app.runtime.agents import (
    PARALLEL_SAFE_ROLES,
    SPECIALISTS,
    Coordinator,
    DraftProjection,
)
from app.runtime.store import event


def test_new_specialists_are_readonly_and_parallel_safe():
    for role in ("profile_cartographer", "role_scout", "curriculum_planner"):
        assert role in SPECIALISTS
        project, _ = SPECIALISTS[role]
        # Extra fields are discarded; the task never sees user_secret.
        scoped = project({
            "skill_names": ["Python"], "evidence_ids": ["e1"],
            "user_secret": "must-not-pass", "upload_bytes": b"raw",
        })
        assert "user_secret" not in scoped
        assert "upload_bytes" not in scoped
    assert PARALLEL_SAFE_ROLES == {"role_scout", "curriculum_planner"}


async def test_budget_is_configurable_and_enforced():
    events = []

    async def progress(name, status, **data):
        events.append((name, status, data))

    coordinator = Coordinator(progress, budget=1)
    await coordinator.delegate("profile_cartographer", {"skill_names": ["Python"]})
    with pytest.raises(ValueError, match="budget exhausted"):
        await coordinator.delegate("profile_cartographer", {"skill_names": ["Python"]})


async def test_delegate_failure_emits_failed_step():
    events = []

    async def progress(name, status, **data):
        events.append((name, status, data))

    coordinator = Coordinator(progress, budget=2)
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # VerificationTask requires allowed_ids and citation_ids; omitting them
        # fails Pydantic projection and must produce a failed terminal event.
        await coordinator.delegate("evidence_verifier", {"citation_ids": ["e1"]})
    assert events[-1][0] == "evidence_verifier"
    assert events[-1][1] == "failed"
    assert "error_type" in events[-1][2]


async def test_delegate_many_runs_independent_roles():
    events = []

    async def progress(name, status, **data):
        events.append((name, status, data))

    coordinator = Coordinator(progress, budget=3)
    inputs = {
        "skill_names": ["Python", "FastAPI"],
        "evidence_ids": ["e1", "e2"],
        "gaps": ["RAG"],
        "weekly_hours": 8,
    }
    results = await coordinator.delegate_many(["role_scout", "curriculum_planner"], inputs)
    assert set(results) == {"role_scout", "curriculum_planner"}
    assert results["role_scout"]["suggestions"]
    assert all(row["url"].startswith("https://") for row in results["curriculum_planner"]["drafts"])
    assert coordinator._remaining == 1


async def test_parallel_progress_event_seq_is_unique():
    """Event seq comes from an atomic SQL increment, not an ORM counter.

    A file-backed SQLite database with a busy timeout serialises the concurrent
    writers so each UPDATE ... RETURNING gets a distinct, consecutive value.
    The old ``run.event_seq += 1`` could hand the same seq to two writers.
    """
    import tempfile
    from pathlib import Path

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(text("PRAGMA journal_mode=WAL"))
            await connection.execute(text("PRAGMA busy_timeout=5000"))
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            session.add(AgentRun(
                id="parallel-run", user_id="parallel-user", operation="job_analysis",
                status="running", request_key="pk", request_hash="ph",
                payload={}, created_at=datetime.now(UTC),
                lease_owner="test-worker", lease_until=int(datetime.now(UTC).timestamp()) + 30,
            ))
            await session.commit()

        async def append(index):
            async with factory() as session:
                current = await session.get(AgentRun, "parallel-run")
                await event(session, current, "step.succeeded", step=f"role-{index}")
                await session.commit()

        await asyncio.gather(*(append(index) for index in range(8)))
        async with factory() as session:
            seqs = list(await session.scalars(
                select(RunEvent.seq)
                .where(RunEvent.run_id == "parallel-run")
                .order_by(RunEvent.seq)
            ))
            stored = await session.scalar(
                select(AgentRun.event_seq).where(AgentRun.id == "parallel-run")
            )
        await engine.dispose()

    assert len(seqs) == 8
    assert seqs == list(range(1, 9))
    assert stored == 8


def test_draft_projection_requires_no_session():
    with pytest.raises(ValidationError):
        DraftProjection.model_validate({
            "skill_names": ["Python"] * 200,
            "evidence_ids": ["e1"],
        })
