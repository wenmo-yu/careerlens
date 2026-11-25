"""HY4-C: saved JDs and learning progress cannot manufacture capability facts."""

from app.models.learning import LearningProgress, SavedJob
from app.security import Principal
from app.services.privacy import delete_user_account, export_user_data


async def test_saved_jobs_dedupe_and_compare(client):
    user_id = "saved-jobs"
    payload = {"user_id": user_id, "title": "Agent 开发", "jd_text": "要求 Python、FastAPI。"}
    for _ in range(2):
        response = await client.post("/api/v1/saved-jobs", json=payload)
        assert response.status_code == 200, response.text
    listed = await client.get("/api/v1/saved-jobs", params={"user_id": user_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    second = await client.post("/api/v1/saved-jobs", json={
        **payload, "title": "LLM 应用", "jd_text": "要求 RAG、Qdrant。",
    })
    assert second.status_code == 200
    compare = await client.get("/api/v1/saved-jobs/compare", params={"user_id": user_id})
    assert compare.status_code == 200
    assert compare.json()["count"] == 2
    assert "重复要求" in compare.json()["note"]


async def test_progress_only_links_existing_evidence(client):
    user_id = "progress-user"
    created = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": user_id, "content": "我用 RAG 做过检索。"},
    )
    assert created.status_code == 201
    e_real = created.json()["items"][0]["id"]

    response = await client.post(
        "/api/v1/learning/plans/plan1/progress",
        params={"user_id": user_id},
        json={"skill": "RAG", "stage": 1, "status": "待提交作品",
              "evidence_ids": [e_real], "actual_hours": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "待提交作品"

    bad = await client.post(
        "/api/v1/learning/plans/plan1/progress",
        params={"user_id": user_id},
        json={"skill": "RAG", "stage": 2, "status": "已核对", "evidence_ids": ["not-mine"]},
    )
    assert bad.status_code == 422

    bad_status = await client.post(
        "/api/v1/learning/plans/plan1/progress",
        params={"user_id": user_id},
        json={"skill": "RAG", "stage": 2, "status": "已完成"},
    )
    assert bad_status.status_code == 422

    plan = await client.get("/api/v1/learning/plans/plan1", params={"user_id": user_id})
    assert plan.status_code == 200
    assert plan.json()["items"][0]["evidence_ids"] == [e_real]


async def test_new_tables_are_exported_and_deleted(session_factory):
    user_id = "hy4-privacy"
    async with session_factory() as session:
        session.add_all([
            SavedJob(
                id="sj1", user_id=user_id, title="JD",
                jd_text="要求 Python", source_hash="h1",
            ),
            LearningProgress(id="lp1", user_id=user_id, plan_id="p1", skill="Python", stage=1),
        ])
        await session.commit()
        principal = Principal(
            user_id=user_id, token_id=None,
            scopes=("read", "write", "export", "delete", "manage"),
        )
        exported = await export_user_data(session, principal=principal)
        assert exported["schema_version"] == "1.0"
        assert exported["saved_jobs"][0]["title"] == "JD"
        assert exported["learning_progress"][0]["skill"] == "Python"

        deleted = await delete_user_account(session, principal=principal)
        assert deleted["deleted_counts"]["saved_jobs"] == 1
        assert deleted["deleted_counts"]["learning_progress"] == 1
        assert await session.get(SavedJob, "sj1") is None
        assert await session.get(LearningProgress, "lp1") is None
