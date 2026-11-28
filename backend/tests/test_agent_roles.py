"""M8 role lifecycle: versioned config, narrowed tools, no escalation."""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import app
from app.runtime.agent import roles as role_service


@pytest_asyncio.fixture
async def api():
    """HTTP client sharing one in-memory DB with direct service access."""

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
async def test_role_create_defaults_read_only_and_rejects_unknown_tool(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="reviewer",
            template="evidence_reviewer",
            prompt=None,
            tool_allowlist=None,
            model_policy=None,
            budget=None,
            output_schema=None,
            actor_token_id="tok-1",
        )
        assert role.version == 1
        assert role.state == "active"
        assert role.session_id
        assert set(role.tool_allowlist) == {"search_evidence", "get_profile"}

        with pytest.raises(role_service.RoleConflict) as exc:
            await role_service.create_role(
                session,
                user_id="u1",
                workspace_id="default",
                name="escalated",
                template="career_coach",
                prompt=None,
                tool_allowlist=["delete_account"],
                actor_token_id="tok-1",
            )
        assert "unknown_tool" in str(exc.value)

        with pytest.raises(role_service.RoleConflict) as exc:
            await role_service.create_role(
                session,
                user_id="u1",
                workspace_id="default",
                name="reviewer",
                template="career_coach",
                prompt=None,
                tool_allowlist=None,
                actor_token_id="tok-1",
            )
        assert "role_name_conflict" in str(exc.value)


@pytest.mark.asyncio
async def test_role_update_bumps_version_and_snapshot_is_frozen(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="coach",
            template="career_coach",
            prompt=None,
            tool_allowlist=None,
            actor_token_id="tok-1",
        )
        before = role_service.role_snapshot(role)

        updated = await role_service.update_role(
            session,
            user_id="u1",
            role_id=role.id,
            prompt="新的提示词",
            tool_allowlist=["search_evidence"],
        )
        assert updated.version == 2
        assert updated.tool_allowlist == ["search_evidence"]
        assert before["role_version"] == 1
        assert before["tool_allowlist"] == ["search_evidence", "get_profile"]


@pytest.mark.asyncio
async def test_trigger_records_role_snapshot_and_is_idempotent(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="analyst",
            template="job_analyst",
            prompt=None,
            tool_allowlist=None,
            actor_token_id=None,
        )
        record, run, created = await role_service.trigger(
            session,
            user_id="u1",
            role_id=role.id,
            text="分析这份 JD",
            request_key="k-1",
            actor_token_id=None,
        )
        assert created is True
        assert run.executor_kind == "agent"
        assert run.payload["role"]["role_id"] == role.id
        assert run.payload["role"]["role_version"] == 1

        _record, run_again, created_again = await role_service.trigger(
            session,
            user_id="u1",
            role_id=role.id,
            text="分析这份 JD",
            request_key="k-1",
            actor_token_id=None,
        )
        assert created_again is False
        assert run_again.id == run.id


@pytest.mark.asyncio
async def test_inactive_role_rejects_trigger(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="planner",
            template="learning_planner",
            prompt=None,
            tool_allowlist=None,
            actor_token_id=None,
        )
        await role_service.set_state(
            session, user_id="u1", role_id=role.id, state="paused"
        )
        with pytest.raises(role_service.RoleConflict) as exc:
            await role_service.trigger(
                session,
                user_id="u1",
                role_id=role.id,
                text="制定计划",
                request_key="k-2",
                actor_token_id=None,
            )
        assert "role_inactive" in str(exc.value)


@pytest.mark.asyncio
async def test_gateway_narrows_tools_for_role_run(api):
    """A role run cannot invoke a tool outside its frozen allowlist."""

    from app.runtime.agent import capability, store

    client, factory = api
    async with factory.begin() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="scoped",
            template="evidence_researcher",
            prompt=None,
            tool_allowlist=["search_evidence"],
            actor_token_id=None,
        )
        _record, run, _created = await role_service.trigger(
            session,
            user_id="u1",
            role_id=role.id,
            text="查证据",
            request_key="k-scoped",
            actor_token_id=None,
        )
        run_id = run.id
        session_id = run.session_id

    # Drive the run to a real running state through the same claim/ack path the
    # scheduler uses, so the capability check accepts the token.
    async with factory.begin() as session:
        claim = await store.claim_agent_run(session, owner="scheduler", max_running=2)
        generation = await store.bind_generation(session, claim=claim)
    async with factory.begin() as session:
        await store.acknowledge(
            session, claim=claim, generation=generation, slot_id="slot-1"
        )

    token = capability.issue(
        user_id="u1",
        session_id=session_id,
        run_id=run_id,
        attempt=claim.attempt,
        runtime_generation=generation,
    )
    headers = {"X-Agent-Capability": token}

    blocked = await client.post(
        "/internal/agent/tools/invoke",
        headers=headers,
        json={"name": "get_profile", "args": {}},
    )
    assert blocked.status_code == 200
    assert blocked.json()["ok"] is False
    assert blocked.json()["code"] == "tool_not_allowed"

    allowed = await client.post(
        "/internal/agent/tools/invoke",
        headers=headers,
        json={"name": "search_evidence", "args": {"query": "Docker"}},
    )
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True
