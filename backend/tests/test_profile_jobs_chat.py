async def _seed_profile(client):
    response = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "career-user",
            "source_type": "resume",
            "source_name": "resume.md",
            "content": (
                "使用 Python、FastAPI 和 LangGraph 构建 AI Agent；"
                "使用 Qdrant 实现 RAG，并通过 Docker 完成部署。"
            ),
        },
    )
    assert response.status_code == 201
    response = await client.post("/api/v1/profiles/career-user/rebuild")
    assert response.status_code == 200
    return response.json()


async def test_rebuild_profile_has_evidence_links(client):
    profile = await _seed_profile(client)
    names = {item["name"] for item in profile["items"]}
    assert {"Python", "FastAPI", "LangGraph", "Qdrant", "RAG"} <= names
    assert all(item["evidence_ids"] for item in profile["items"])


async def test_job_analysis_marks_supported_and_gap_requirements(client):
    await _seed_profile(client)
    response = await client.post(
        "/api/v1/jobs/analyze",
        json={
            "user_id": "career-user",
            "title": "AI Agent 开发实习生",
            "jd_text": "要求熟悉 Python、FastAPI、LangGraph、RAG 和 Kubernetes，Docker 优先。",
            "weekly_hours": 8,
        },
    )
    assert response.status_code == 200
    result = response.json()
    matches = {item["name"]: item for item in result["matches"]}
    assert matches["Python"]["status"] in {"strong", "partial"}
    assert matches["Kubernetes"]["status"] == "gap"
    assert "SQL" not in matches
    assert result["learning_path"][0]["skill"] == "Kubernetes"


async def test_career_report_is_versioned_traceable_and_downloadable(client):
    await _seed_profile(client)
    analysis_response = await client.post(
        "/api/v1/jobs/analyze",
        json={
            "user_id": "career-user",
            "title": "AI Agent 开发实习生",
            "jd_text": "要求熟悉 Python、FastAPI、LangGraph、RAG 和 Kubernetes，Docker 优先。",
            "weekly_hours": 8,
        },
    )
    analysis_id = analysis_response.json()["id"]
    response = await client.post(
        "/api/v1/reports",
        json={"user_id": "career-user", "job_analysis_id": analysis_id},
    )
    assert response.status_code == 201
    report = response.json()
    assert report["version"] == 1
    assert report["is_stale"] is False
    assert report["content"]["skill_gaps"][0]["name"] == "Kubernetes"
    assert report["content"]["evidence_catalog"]
    assert "## 08 求职行动建议" in report["markdown"]
    assert report["model_diagnostics"]["provider"] == "demo"

    second = await client.post(
        "/api/v1/reports",
        json={"user_id": "career-user", "job_analysis_id": analysis_id},
    )
    assert second.json()["version"] == 2

    reports = await client.get("/api/v1/reports", params={"user_id": "career-user"})
    assert [item["version"] for item in reports.json()] == [2, 1]
    markdown = await client.get(f"/api/v1/reports/{report['id']}/markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Evidence-grounded" in markdown.text

    evidence_id = report["content"]["evidence_catalog"][0]["id"]
    deleted = await client.delete(f"/api/v1/evidence/{evidence_id}")
    assert deleted.status_code == 200
    assert deleted.json()["stale_reports"] == 2
    refreshed = await client.get(f"/api/v1/reports/{report['id']}")
    assert refreshed.json()["is_stale"] is True


async def test_career_chat_returns_traceable_evidence(client):
    await _seed_profile(client)
    response = await client.post(
        "/api/v1/chat",
        json={"user_id": "career-user", "message": "为什么认为我会 LangGraph？"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["intent"] == "evidence_explanation"
    assert result["evidence"]
    assert result["retrieval"]["backend"] == "local"
    assert result["retrieval"]["fallback"] is True


async def test_chat_persists_history_across_turns(client):
    """Multiple turns in one thread accumulate durable messages (F02/F03)."""
    await _seed_profile(client)
    first = await client.post(
        "/api/v1/chat",
        json={"user_id": "career-user", "message": "我适合什么方向？"},
    )
    assert first.status_code == 200
    first_body = first.json()
    thread_id = first_body["thread_id"]
    assert [m["role"] for m in first_body["messages"]] == ["user", "assistant"]
    assert first_body["messages"][0]["content"] == "我适合什么方向？"

    second = await client.post(
        "/api/v1/chat",
        json={
            "user_id": "career-user",
            "message": "那我还需要补什么？",
            "thread_id": thread_id,
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["thread_id"] == thread_id
    roles = [m["role"] for m in second_body["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert second_body["messages"][2]["content"] == "那我还需要补什么？"


async def test_chat_history_is_isolated_between_threads_and_users(client):
    await _seed_profile(client)
    a = (await client.post(
        "/api/v1/chat",
        json={"user_id": "career-user", "message": "第一个会话的问题"},
    )).json()
    b = (await client.post(
        "/api/v1/chat",
        json={"user_id": "career-user", "message": "另一个会话的问题"},
    )).json()
    assert a["thread_id"] != b["thread_id"]
    assert len(a["messages"]) == 2
    assert len(b["messages"]) == 2
    assert a["messages"][0]["content"] == "第一个会话的问题"
    assert b["messages"][0]["content"] == "另一个会话的问题"
