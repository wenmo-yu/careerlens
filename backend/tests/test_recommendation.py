"""HY4-C: recommendations must stay traceable to Evidence and never fetch URLs."""

from datetime import UTC, datetime

from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.services.recommendation import (
    build_learning_plan_v2,
    recommend_courses,
    recommend_roles,
)


def _item(item_id, category, name, confidence=0.9, evidence_ids=None, details=None):
    return ProfileItem(
        id=item_id, user_id="u1", category=category, name=name, level=4,
        confidence=confidence, evidence_ids=evidence_ids or [], details=details or {},
    )


def _evidence(evidence_id, content="我用 Python 做过项目"):
    return Evidence(
        id=evidence_id, user_id="u1", source_type="self_statement", source_name="cv",
        content=content, content_hash=evidence_id, created_at=datetime.now(UTC),
    )


def test_role_recommendations_are_grounded_in_live_evidence():
    items = [
        _item("p1", "skill", "Python", evidence_ids=["e1"]),
        _item("p2", "skill", "LangGraph", evidence_ids=["e2"]),
        _item("p3", "skill", "RAG", evidence_ids=["e3"]),
        _item("p4", "skill", "FastAPI", evidence_ids=["e4"]),
        _item("p5", "interest", "MBTI INTP", evidence_ids=["e1"]),
    ]
    evidence = [_evidence(f"e{i}") for i in range(1, 5)]
    rows = recommend_roles(items, evidence, limit=3)
    assert rows
    top = rows[0]
    assert top["role_id"] == "ai-agent-dev"
    assert set(top["matched_required"]) == {"python", "langgraph", "rag", "fastapi"}
    assert set(top["evidence_ids"]) == {"e1", "e2", "e3", "e4"}
    assert "10" not in str(top)  # no personality tag leaked into the reason
    assert "本地教学模板" in top["source_note"]


def test_role_recommendations_drop_deleted_evidence():
    items = [_item("p1", "skill", "Python", evidence_ids=["missing"])]
    assert recommend_roles(items, []) == []


def test_course_recommendations_respect_weekly_budget():
    rows = recommend_courses("RAG", weekly_hours=3)
    assert rows
    assert all(row["url"].startswith("https://") for row in rows)
    assert all("prerequisite_note" in row for row in rows)
    assert sum(row["estimated_hours"] for row in rows) <= 6


def test_learning_plan_v2_enriches_without_changing_order():
    existing = [
        {"stage": 1, "skill": "RAG", "current_level": 2, "weeks": 2,
         "goal": "补齐 RAG", "deliverables": ["跑通检索"], "source_evidence_ids": ["e1"]},
        {"stage": 2, "skill": "Docker", "current_level": 1, "weeks": 1,
         "goal": "部署服务", "deliverables": ["容器运行"], "source_evidence_ids": []},
    ]
    rows = build_learning_plan_v2(
        existing, [_item("p1", "skill", "RAG", evidence_ids=["e1"])], {"e1"}
    )
    assert [row["stage"] for row in rows] == [1, 2]
    assert [row["skill"] for row in rows] == ["RAG", "Docker"]
    assert rows[0]["target_level"] == 3
    assert rows[0]["resources"][0]["course_id"]
    assert rows[0]["progress_status"] == "待开始"
    assert rows[0]["verification"]


async def test_recommendation_endpoints(client):
    user_id = "rec-user"
    response = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": user_id,
            "content": "我用 Python、LangGraph、RAG 与 FastAPI 构建过 Agent 应用。",
        },
    )
    assert response.status_code == 201
    assert (await client.post(f"/api/v1/profiles/{user_id}/rebuild")).status_code == 200
    roles = await client.post(
        "/api/v1/recommendations/roles", json={"user_id": user_id, "limit": 3}
    )
    assert roles.status_code == 200, roles.text
    assert roles.json()[0]["evidence_ids"]


async def test_recommendations_require_a_profile(client):
    roles = await client.post("/api/v1/recommendations/roles", json={"user_id": "no-profile"})
    assert roles.status_code == 422
