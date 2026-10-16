import json

import httpx

from app.llm.provider import OpenAICompatibleProvider


async def test_openai_compatible_provider_parses_structured_json():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '```json\n{"answer":"ok"}\n```'}}]},
        )

    provider = OpenAICompatibleProvider(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_key="secret",
        model="deepseek-flash",
        timeout=10,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_json(
        system_prompt="system", user_prompt="user", schema={"type": "object"}
    )
    assert result == {"answer": "ok"}


async def test_profile_update_requires_confirmation(client):
    imported = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "memory-user",
            "source_type": "self_statement",
            "source_name": "test",
            "content": "我使用 Python 和 FastAPI 开发应用。",
        },
    )
    assert imported.status_code == 201
    assert (await client.post("/api/v1/profiles/memory-user/rebuild")).status_code == 200

    created = await client.post(
        "/api/v1/profiles/memory-user/proposals",
        json={"message": "我更希望 AI Agent 应用开发"},
    )
    assert created.status_code == 200
    proposal = created.json()
    assert proposal["status"] == "pending"
    assert proposal["changes"][0]["name"] == "AI Agent 应用开发"
    before = (await client.get("/api/v1/profiles/memory-user")).json()
    assert all(item["name"] != "AI Agent 应用开发" for item in before["items"])

    approved = await client.post(
        f"/api/v1/profiles/proposals/{proposal['id']}/decision", json={"approve": True}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    after = (await client.get("/api/v1/profiles/memory-user")).json()
    target = next(item for item in after["items"] if item["name"] == "AI Agent 应用开发")
    assert target["category"] == "target_role"
    assert target["evidence_ids"]


async def test_rejected_profile_update_does_not_change_profile(client):
    created = await client.post(
        "/api/v1/profiles/reject-user/proposals",
        json={"message": "我想做数据分析"},
    )
    proposal = created.json()
    rejected = await client.post(
        f"/api/v1/profiles/proposals/{proposal['id']}/decision", json={"approve": False}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    profile = (await client.get("/api/v1/profiles/reject-user")).json()
    assert profile["count"] == 0
