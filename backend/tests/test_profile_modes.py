"""HY4-D: display modes and stories never alter facts or match scores."""

import json

from app.services.profile_view_preferences import (
    DEFAULT_MODULES,
    MODES,
    default_modules,
    normalise_mode,
)


def test_mode_defaults_and_validation():
    assert normalise_mode(None) == "job_search"
    assert normalise_mode("unknown") == "job_search"
    assert set(MODES) == {
        "job_search", "career_change", "capability_audit", "learning_plan", "minimal"
    }
    assert default_modules() == DEFAULT_MODULES
    assert default_modules()["skill_matrix"] is True
    assert default_modules()["interview_stories"] is False


async def test_view_preferences_roundtrip(client):
    user_id = "mode-user"
    response = await client.put(
        f"/api/v1/profiles/{user_id}/view-preferences",
        json={
            "user_id": user_id, "mode": "career_change",
            "modules": {"interview_stories": True, "minimal": True, "skill_matrix": False},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "career_change"
    assert payload["modules"]["interview_stories"] is True
    assert payload["modules"]["skill_matrix"] is False
    assert "minimal" not in payload["modules"]  # unknown key ignored

    fetched = await client.get(
        f"/api/v1/profiles/{user_id}/view-preferences", params={"user_id": user_id}
    )
    assert fetched.status_code == 200
    assert fetched.json()["mode_label"] == "转行探索"
    assert [item["key"] for item in fetched.json()["available_modes"]] == list(MODES)


async def test_preferences_do_not_change_profile_or_coverage(client):
    user_id = "mode-facts"
    created = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": user_id, "content": "我用 Python 与 FastAPI 做过 Agent。"},
    )
    assert created.status_code == 201
    assert (await client.post(f"/api/v1/profiles/{user_id}/rebuild")).status_code == 200
    before = (await client.get(f"/api/v1/profiles/{user_id}/overview")).json()

    for mode in MODES:
        response = await client.put(
            f"/api/v1/profiles/{user_id}/view-preferences",
            json={"user_id": user_id, "mode": mode, "modules": {"interview_stories": True}},
        )
        assert response.status_code == 200

    after = (await client.get(f"/api/v1/profiles/{user_id}/overview")).json()
    assert after["coverage"] == before["coverage"]
    assert after["by_category"] == before["by_category"]
    assert after["profile_item_count"] == before["profile_item_count"]


async def test_interview_story_must_anchor_to_own_evidence(client):
    owner = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "story-owner", "content": "我用 RAG 做过检索系统。"},
    )
    evidence_id = owner.json()["items"][0]["id"]

    rejected = await client.post(
        "/api/v1/profiles/story-user/interview-stories",
        json={
            "user_id": "story-user", "title": "检索项目", "action": "做过 RAG",
            "evidence_ids": [evidence_id],
        },
    )
    assert rejected.status_code == 422

    accepted = await client.post(
        "/api/v1/profiles/story-owner/interview-stories",
        json={
            "user_id": "story-owner", "title": "检索项目",
            "situation": "课程项目需要检索", "action": "用 RAG 搭检索", "result": "可回查证据",
            "evidence_ids": [evidence_id],
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "证据支持"

    listed = await client.get(
        "/api/v1/profiles/story-owner/interview-stories",
        params={"user_id": "story-owner"},
    )
    assert listed.status_code == 200
    assert listed.json()["stories"][0]["evidence_ids"] == [evidence_id]
    assert listed.json()["stories"][0]["action"] == "用 RAG 搭检索"


async def test_story_without_evidence_is_marked_pending(client):
    response = await client.post(
        "/api/v1/profiles/no-evidence/interview-stories",
        json={"user_id": "no-evidence", "title": "待核对故事", "action": "大概做过"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "待补证据"


def test_view_preferences_are_serialisable():
    payload = json.dumps(default_modules(), ensure_ascii=False)
    assert json.loads(payload)["skill_matrix"] is True
