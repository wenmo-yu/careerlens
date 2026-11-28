"""M8 wake reconciliation: missed-due strategy, idempotency, explainable reports."""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import app
from app.models.schedule import AgentScheduleOccurrence
from app.runtime.agent import schedule as schedule_service
from app.runtime.agent import wake as wake_service


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_wake_route_rejects_inverted_window(api):
    client, _factory = api
    response = await client.post(
        "/api/v1/agent/wake/reconcile?user_id=u1",
        json={"last_seen": 200, "now": 100},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_wake_route_reconciles_and_lists_reports(api):
    client, factory = api
    async with factory.begin() as session:
        await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="route-gap",
            prompt="x",
            interval_seconds=60,
            misfire_policy="run_once",
            actor_token_id=None,
            start_at=100,
        )
    response = await client.post(
        "/api/v1/agent/wake/reconcile?user_id=u1",
        json={"last_seen": 100, "now": 10000},
    )
    assert response.status_code == 201
    assert response.json()["triggered"] == 1

    listed = await client.get("/api/v1/agent/wake/reports?user_id=u1")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["observed_gap_seconds"] == 9900


@pytest.mark.asyncio
async def test_reconcile_applies_skip_and_run_once(session_factory):
    async with session_factory() as session:
        skipped = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="skip-plan",
            prompt="x",
            interval_seconds=60,
            misfire_policy="skip",
            actor_token_id=None,
            start_at=100,
        )
        once = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="once-plan",
            prompt="y",
            interval_seconds=60,
            misfire_policy="run_once",
            actor_token_id=None,
            start_at=100,
        )
        # Machine "away" from 100 to 10000; two intervals were missed.
        report = await wake_service.reconcile(session, last_seen=100, now=10000)
        assert report.observed_gap_seconds == 9900
        assert report.missed_due == 2
        assert report.skipped == 1  # skip policy: only a skipped occurrence
        assert report.triggered == 1  # run_once: one compensation run
        assert skipped.next_due > 10000
        assert once.next_due > 10000


@pytest.mark.asyncio
async def test_reconcile_is_idempotent_for_same_window(session_factory):
    async with session_factory() as session:
        await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="once",
            prompt="y",
            interval_seconds=60,
            misfire_policy="run_once",
            actor_token_id=None,
            start_at=100,
        )
        first = await wake_service.reconcile(session, last_seen=100, now=200)
        second = await wake_service.reconcile(session, last_seen=100, now=200)
        occurrences = list(
            await session.scalars(
                select_occurrences(session, "u1")
            )
        )
        runs = {item.run_id for item in occurrences if item.run_id}
        assert first.triggered == 1
        assert len(runs) == 1  # no duplicate run for the same due
        assert second.triggered == 0  # next_due already advanced past the window


def select_occurrences(session, user_id):
    from sqlalchemy import select

    return select(AgentScheduleOccurrence).where(
        AgentScheduleOccurrence.user_id == user_id
    )


@pytest.mark.asyncio
async def test_reconcile_rejects_inverted_window(session_factory):
    async with session_factory() as session:
        with pytest.raises(wake_service.WakeConflict):
            await wake_service.reconcile(session, last_seen=200, now=100)
        assert await wake_service.list_reports(session) == []


@pytest.mark.asyncio
async def test_scheduler_startup_reconciles_the_downtime_gap(session_factory):
    """Restarting the scheduler explains and compensates a missed due time."""

    from app.models.heartbeat import RuntimeHeartbeat
    from app.runtime.agent.scheduler import AgentScheduler, SchedulerConfig
    from app.runtime.store import now_seconds

    moment = now_seconds()
    async with session_factory.begin() as session:
        schedule = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="停机期间到期",
            prompt="x",
            interval_seconds=60,
            misfire_policy="run_once",
            actor_token_id=None,
            start_at=moment - 30,
        )
        # The previous instance last beat 60s ago, so its due time fell inside
        # the downtime window [last_seen, now].
        session.add(
            RuntimeHeartbeat(
                role="scheduler",
                instance_id="previous-instance",
                pid=1,
                heartbeat_at=moment - 60,
                started_at=moment - 600,
            )
        )
        await session.flush()

    scheduler = AgentScheduler(
        session_factory,
        config=SchedulerConfig(poll_seconds=0.01),
        cli_command=["python", "-c", "pass"],
        api_base="http://127.0.0.1:9",
    )
    await scheduler.startup()

    async with session_factory() as session:
        reports = await wake_service.list_reports(session)
        assert len(reports) == 1
        assert reports[0].missed_due == 1
        assert reports[0].triggered == 1
        occurrences = list(
            await session.scalars(
                select_occurrences(session, "u1")
            )
        )
        assert [item.status for item in occurrences] == ["claimed"]
        refreshed = await session.get(type(schedule), schedule.id)
        assert refreshed.next_due > moment
