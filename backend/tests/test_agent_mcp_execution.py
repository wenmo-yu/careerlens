"""M8 controlled MCP execution: namespaced calls pass admission, fail closed."""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import app
from app.models.agent import AgentSession
from app.runtime.agent import mcp_connectors as connectors
from app.runtime.agent import mcp_execution


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


def test_is_mcp_tool():
    assert mcp_execution.is_mcp_tool("docs.search") is True
    assert mcp_execution.is_mcp_tool("search_evidence") is False
    assert mcp_execution.is_mcp_tool("9bad.tool") is False


@pytest.mark.asyncio
async def test_unregistered_namespace_is_denied(session_factory):
    async with session_factory() as session:
        decision = await mcp_execution.execute(
            session, user_id="u1", qualified_name="ghost.search"
        )
        assert decision.handled is True
        assert decision.ok is False
        assert decision.code == "connector_not_found"


@pytest.mark.asyncio
async def test_disabled_connector_is_denied(session_factory):
    async with session_factory() as session:
        await connectors.register(
            session, user_id="u1", workspace_id="default", namespace="docs",
            allowed_tools=["search"], required_scope="read",
        )
        decision = await mcp_execution.execute(
            session, user_id="u1", qualified_name="docs.search"
        )
        assert decision.ok is False
        assert decision.code == "connector_disabled"


@pytest.mark.asyncio
async def test_admitted_tool_still_fails_closed_without_sandbox(session_factory):
    async with session_factory() as session:
        record = await connectors.register(
            session, user_id="u1", workspace_id="default", namespace="docs",
            allowed_tools=["search"], required_scope="read",
        )
        await connectors.set_state(session, user_id="u1", connector_id=record.id, state="enabled")
        decision = await mcp_execution.execute(
            session, user_id="u1", qualified_name="docs.search", caller_scopes={"read"}
        )
        assert decision.ok is False
        assert decision.code == "execution_unavailable"
        assert "sandbox" in decision.message.lower()


@pytest.mark.asyncio
async def test_gateway_routes_namespaced_tool_through_admission(api):
    """The CLI gateway must not hand a namespaced MCP tool to built-in tools."""

    from app.runtime.agent import capability, store

    client, factory = api
    async with factory.begin() as session:
        record = await connectors.register(
            session, user_id="u1", workspace_id="default", namespace="docs",
            allowed_tools=["search"], required_scope="read",
        )
        await connectors.set_state(
            session, user_id="u1", connector_id=record.id, state="enabled"
        )
        # Use a plain built-in run (no role payload) for the capability handshake.
        session.add(
            AgentSession(id="sess-1", user_id="u1", title="t", workspace_id="default")
        )
        await session.flush()
        run = await store.submit_turn(
            session, user_id="u1", session_id="sess-1", text="x",
            token_id=None, request_key="mcp-gateway-1",
        )
        run_id = run[0].id
    async with factory.begin() as session:
        claim = await store.claim_agent_run(session, owner="scheduler", max_running=2)
        generation = await store.bind_generation(session, claim=claim)
    async with factory.begin() as session:
        await store.acknowledge(session, claim=claim, generation=generation, slot_id="slot-1")
    token = capability.issue(
        user_id="u1", session_id="sess-1", run_id=run_id,
        attempt=claim.attempt, runtime_generation=generation,
    )
    response = await client.post(
        "/internal/agent/tools/invoke",
        headers={"X-Agent-Capability": token},
        json={"name": "docs.search", "args": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "execution_unavailable"


@pytest.mark.asyncio
async def test_gateway_scopes_come_from_the_run_token(api):
    """A write-scoped token cannot widen itself to reach a manage connector."""

    from app.runtime.agent import capability, store
    from app.security.auth import create_access_token

    client, factory = api
    # create_access_token commits, so it must not run inside an open begin() block.
    async with factory() as session:
        access, _raw = await create_access_token(
            session, user_id="u1", name="writer", scopes=["write"]
        )
        token_id = access.id
    async with factory.begin() as session:
        record = await connectors.register(
            session, user_id="u1", workspace_id="default", namespace="docs",
            allowed_tools=["search"], required_scope="manage",
        )
        await connectors.set_state(
            session, user_id="u1", connector_id=record.id, state="enabled"
        )
        session.add(
            AgentSession(id="sess-2", user_id="u1", title="t", workspace_id="default")
        )
        await session.flush()
        run = await store.submit_turn(
            session, user_id="u1", session_id="sess-2", text="x",
            token_id=token_id, request_key="mcp-gateway-2",
        )
        run_id = run[0].id
    async with factory.begin() as session:
        claim = await store.claim_agent_run(session, owner="scheduler", max_running=2)
        generation = await store.bind_generation(session, claim=claim)
    async with factory.begin() as session:
        await store.acknowledge(session, claim=claim, generation=generation, slot_id="slot-1")
    token = capability.issue(
        user_id="u1", session_id="sess-2", run_id=run_id,
        attempt=claim.attempt, runtime_generation=generation,
    )
    response = await client.post(
        "/internal/agent/tools/invoke",
        headers={"X-Agent-Capability": token},
        json={"name": "docs.search", "args": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "scope_insufficient"
