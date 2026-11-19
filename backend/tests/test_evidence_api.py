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


async def test_document_upload_persists_table_and_deduplicates_locations(client):
    user_id = "structured-doc"
    evidence_ids = []
    for filename, data in [
        ("skills.csv", b"Skill,Level\nPython,Advanced\n"),
        ("skills.csv", b"Skill,Level\nPython,Advanced"),
        ("copy.csv", b"Skill,Level\nPython,Advanced\n"),
    ]:
        response = await client.post(
            "/api/v1/evidence/file",
            data={"user_id": user_id},
            files={"upload": (filename, data, "text/csv")},
        )
        assert response.status_code == 201
        evidence_ids.append(response.json()["items"][0]["id"])

    assert len(set(evidence_ids)) == 1
    export_url = f"/api/v1/privacy/{user_id}/export"
    exported = (await client.get(export_url)).json()
    assert len(exported["source_documents"]) == 2
    assert len(exported["parsed_blocks"]) == 2
    assert len(exported["evidence"][0]["source_metadata"]["sources"]) == 3
    for block in exported["parsed_blocks"]:
        assert block["block_type"] == "table"
        assert block["evidence_id"] == evidence_ids[0]
        assert "| Python | Advanced |" in block["content"]

    await client.delete(f"/api/v1/evidence/{evidence_ids[0]}")
    assert (await client.get(export_url)).json()["parsed_blocks"] == []
