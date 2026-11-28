import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.main import app
from app.runtime.agent import capability, store


@pytest_asyncio.fixture
async def agent_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def create_turn(client, factory, *, user="agent-user", text="Docker 证据"):
    response = await client.post("/api/v1/agent/sessions", json={"user_id": user, "title": "t"})
    assert response.status_code == 201
    session_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/agent/sessions/{session_id}/runs",
        json={"user_id": user, "text": text},
        headers={"Idempotency-Key": "turn-1"},
    )
    assert response.status_code == 202
    run = response.json()
    async with factory.begin() as session:
        claim = await store.claim_agent_run(session, owner="scheduler", max_running=2)
        generation = await store.bind_generation(session, claim=claim)
    async with factory.begin() as session:
        await store.acknowledge(
            session, claim=claim, generation=generation, slot_id="slot-1"
        )
    return session_id, run["id"], claim, generation


async def test_session_turn_and_history(agent_api):
    client, factory = agent_api
    session_id, run_id, _, _ = await create_turn(client, factory)

    response = await client.get(
        f"/api/v1/agent/sessions/{session_id}/messages", params={"user_id": "agent-user"}
    )
    assert response.status_code == 200
    messages = response.json()
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "Docker 证据")
    ]

    response = await client.get(
        f"/api/v1/agent/sessions/{session_id}", params={"user_id": "agent-user"}
    )
    assert response.json()["head_revision"] == 1

    response = await client.get(
        f"/api/v1/agent/sessions/{session_id}", params={"user_id": "someone-else"}
    )
    assert response.status_code == 404

    response = await client.get(f"/api/v1/runs/{run_id}", params={"user_id": "agent-user"})
    assert response.json()["executor_kind"] == "agent"


async def test_internal_gateway_requires_a_matching_capability(agent_api):
    client, factory = agent_api
    _, run_id, claim, generation = await create_turn(client, factory)
    token = capability.issue(
        user_id=claim.user_id,
        session_id=claim.session_id,
        run_id=run_id,
        attempt=claim.attempt,
        runtime_generation=generation,
    )
    body = {"messages": [{"role": "user", "content": "Docker"}], "tools": []}

    response = await client.post("/internal/agent/model/complete", json=body)
    assert response.status_code == 401

    response = await client.post(
        "/internal/agent/model/complete",
        json=body,
        headers={"X-Agent-Capability": token[:-3] + "abc"},
    )
    assert response.status_code == 401

    stale = capability.issue(
        user_id=claim.user_id,
        session_id=claim.session_id,
        run_id=run_id,
        attempt=claim.attempt + 1,
        runtime_generation=generation,
    )
    response = await client.post(
        "/internal/agent/model/complete",
        json=body,
        headers={"X-Agent-Capability": stale},
    )
    assert response.status_code == 409


async def test_internal_model_streams_deltas_and_tool_calls(agent_api):
    client, factory = agent_api
    _, run_id, claim, generation = await create_turn(client, factory)
    token = capability.issue(
        user_id=claim.user_id,
        session_id=claim.session_id,
        run_id=run_id,
        attempt=claim.attempt,
        runtime_generation=generation,
    )
    payload = {
        "messages": [{"role": "user", "content": "Docker 证据"}],
        "tools": [
            {"name": "search_evidence"},
            {"name": "not_registered"},
        ],
    }
    chunks = []
    async with client.stream(
        "POST",
        "/internal/agent/model/complete",
        json=payload,
        headers={"X-Agent-Capability": token},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for text in response.aiter_text():
            chunks.append(text)
    body = "".join(chunks)
    assert '"type": "tool_call"' in body
    assert '"name": "search_evidence"' in body
    assert "[DONE]" in body


async def test_internal_tool_gateway_rejects_identity_and_returns_results(agent_api):
    client, factory = agent_api
    _, run_id, claim, generation = await create_turn(client, factory)
    token = capability.issue(
        user_id=claim.user_id,
        session_id=claim.session_id,
        run_id=run_id,
        attempt=claim.attempt,
        runtime_generation=generation,
    )
    response = await client.post(
        "/internal/agent/tools/invoke",
        json={"name": "search_evidence", "args": {"query": "Docker"}},
        headers={"X-Agent-Capability": token},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["result"]["items"] == []

    response = await client.post(
        "/internal/agent/tools/invoke",
        json={"name": "search_evidence", "args": {"query": "Docker", "user_id": "victim"}},
        headers={"X-Agent-Capability": token},
    )
    assert response.json() == {
        "ok": False,
        "code": "identity_in_args",
        "message": "user_id must not be supplied by the model",
    }


async def test_approvals_and_runtime_status(agent_api):
    client, factory = agent_api
    _, run_id, claim, generation = await create_turn(client, factory, user="approver")
    async with factory.begin() as session:
        await store.wait_for_approval(
            session,
            claim=claim,
            generation=generation,
            invocation_id="call-9",
            tool="overwrite_profile",
            args_digest="f" * 64,
        )
    response = await client.get("/api/v1/agent/approvals", params={"user_id": "approver"})
    assert [item["invocation_id"] for item in response.json()] == ["call-9"]

    response = await client.post(
        f"/api/v1/agent/approvals/{run_id}/decision",
        json={"user_id": "approver", "approve": False},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    response = await client.get("/api/v1/runtime/status", params={"user_id": "approver"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol"] == 1
    assert payload["runs"]["cancelled"] == 1
    assert payload["pending_approvals"] == 0


async def test_runtime_capabilities_reports_limits(agent_api):
    client, _ = agent_api
    response = await client.get(
        "/api/v1/runtime/capabilities", params={"user_id": "agent-user"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["executor_kinds"] == ["workflow", "agent"]
    assert payload["read_only_tools"] == ["get_profile", "search_evidence"]
    assert payload["limits"]["max_running"] >= 1


async def test_reconnect_replays_events_and_messages_after_cursor(agent_api):
    from app.runtime.agent import store as agent_store

    client, factory = agent_api
    session_id, run_id, claim, generation = await create_turn(client, factory)
    async with factory.begin() as session:
        await agent_store.settle(
            session,
            claim=claim,
            generation=generation,
            stop_reason="completed",
            text="replayed answer",
        )
    response = await client.get(
        f"/api/v1/runs/{run_id}/events",
        params={"user_id": "agent-user", "after_seq": 3},
    )
    kinds = [event["event_type"] for event in response.json()]
    assert kinds[-2:] == ["run.settled", "run.committed"]

    response = await client.get(
        f"/api/v1/agent/sessions/{session_id}/messages",
        params={"user_id": "agent-user", "after_seq": 1},
    )
    assert [item["content"] for item in response.json()] == ["replayed answer"]


async def test_approval_dto_capabilities_and_idempotent_decision(agent_api):
    client, factory = agent_api
    _, run_id, claim, generation = await create_turn(client, factory, user="m5-user")
    async with factory.begin() as session:
        await store.wait_for_approval(
            session,
            claim=claim,
            generation=generation,
            invocation_id="call-10",
            tool="save_career_note",
            args_digest="d" * 64,
            scope="agent.artifact.write",
        )
    response = await client.get("/api/v1/agent/approvals", params={"user_id": "m5-user"})
    assert response.status_code == 200
    item = response.json()[0]
    assert item["invocation_id"] == "call-10"
    assert item["tool"] == "save_career_note"
    assert item["args_digest"] == "d" * 64
    assert item["scope"] == "agent.artifact.write"
    assert "created_at" in item

    response = await client.get(
        "/api/v1/runtime/capabilities", params={"user_id": "m5-user"}
    )
    payload = response.json()
    assert payload["write_tools"] == ["save_career_note"]
    assert payload["tool_ledger"] is True
    assert payload["read_only_tools"] == ["get_profile", "search_evidence"]

    for _ in range(2):
        decision = await client.post(
            f"/api/v1/agent/approvals/{run_id}/decision",
            json={"user_id": "m5-user", "approve": True},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "queued"
    conflict = await client.post(
        f"/api/v1/agent/approvals/{run_id}/decision",
        json={"user_id": "m5-user", "approve": False},
    )
    assert conflict.status_code == 409
