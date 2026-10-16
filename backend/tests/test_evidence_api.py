async def test_ingest_and_list_text_evidence(client):
    response = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "demo-user",
            "source_type": "self_statement",
            "source_name": "goal",
            "content": "我希望从事 AI Agent 与 LLM 应用开发。",
            "metadata": {"language": "zh-CN"},
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["source_metadata"]["language"] == "zh-CN"

    response = await client.get("/api/v1/evidence", params={"user_id": "demo-user"})
    assert response.status_code == 200
    assert response.json()["count"] == 1


async def test_rejects_empty_normalized_content(client):
    response = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "demo-user", "content": "\u0000   "},
    )
    assert response.status_code == 422


async def test_rejects_unsupported_file(client):
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "demo-user", "source_type": "resume"},
        files={"upload": ("resume.exe", b"not a document", "application/octet-stream")},
    )
    assert response.status_code == 422
