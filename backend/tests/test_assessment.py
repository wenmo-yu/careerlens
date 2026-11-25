"""HY4-D: assessments are self-reported, skippable and never become facts."""


from app.models.assessment import AssessmentResult, UserConstraint
from app.models.career_report import CareerReport
from app.models.profile_extension import DimensionDefinition, ProfileExtension
from app.security import Principal
from app.services.assessment import mark_reports_stale
from app.services.privacy import delete_user_account, export_user_data


async def test_questions_are_project_authored_and_skippable(client):
    response = await client.get("/api/v1/assessments/questions/work_preference")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v1"
    assert all("text" in item for item in payload["questions"])
    assert "非官方量表" in payload["note"]


async def test_assessment_requires_consent_and_valid_answers(client):
    no_consent = await client.post(
        "/api/v1/assessments/work_preference/submit",
        json={"user_id": "assess-u1", "instrument": "work_preference",
              "answers": {"deep_focus": 5}, "consent": False},
    )
    assert no_consent.status_code == 422
    bad = await client.post(
        "/api/v1/assessments/work_preference/submit",
        json={"user_id": "assess-u1", "instrument": "work_preference",
              "answers": {"unknown": 5}, "consent": True},
    )
    assert bad.status_code == 422
    ok = await client.post(
        "/api/v1/assessments/work_preference/submit",
        json={"user_id": "assess-u1", "instrument": "work_preference",
              "answers": {"deep_focus": 5, "collaboration": 2}, "consent": True},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"]["top"][0][0] == "deep_focus"


async def test_assessment_does_not_change_skill_coverage(client):
    user_id = "assess-facts"
    created = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": user_id, "content": "我用 Python 与 FastAPI 构建过服务。"},
    )
    assert created.status_code == 201
    assert (await client.post(f"/api/v1/profiles/{user_id}/rebuild")).status_code == 200
    before = (await client.get(f"/api/v1/profiles/{user_id}/overview")).json()

    for instrument, body in (
        ("work_preference", {"answers": {"deep_focus": 5}}),
        ("riasec", {"answers": {"I": 5, "R": 2}}),
        ("mbti_label", {"label": "INTP"}),
    ):
        response = await client.post(
            f"/api/v1/assessments/{instrument}/submit",
            json={"user_id": user_id, "instrument": instrument,
                  "consent": True, **body},
        )
        assert response.status_code == 200, response.text

    after = (await client.get(f"/api/v1/profiles/{user_id}/overview")).json()
    assert after["coverage"] == before["coverage"]
    assert after["profile_item_count"] == before["profile_item_count"]
    assert after["by_category"] == before["by_category"]

    results = await client.get("/api/v1/assessments/results", params={"user_id": user_id})
    assert results.status_code == 200
    assert {row["instrument"] for row in results.json()} >= {
        "work_preference", "riasec", "mbti_label"
    }


async def test_assessment_deletion_and_dimension_toggle(client):
    user_id = "assess-delete"
    submitted = await client.post(
        "/api/v1/assessments/riasec/submit",
        json={"user_id": user_id, "instrument": "riasec",
              "answers": {"I": 5}, "consent": True},
    )
    assert submitted.status_code == 200
    result_id = submitted.json()["id"]
    deleted = await client.delete(
        f"/api/v1/assessments/results/{result_id}", params={"user_id": user_id}
    )
    assert deleted.status_code == 200

    dimension = await client.put(
        f"/api/v1/profiles/{user_id}/dimensions",
        json={"user_id": user_id, "key": "values_growth", "label": "成长偏好",
              "description": "自陈维度", "enabled": True, "value": {"priority": "深度工作"}},
    )
    assert dimension.status_code == 200
    listed = await client.get(f"/api/v1/profiles/{user_id}/dimensions", params={"user_id": user_id})
    assert listed.status_code == 200
    assert listed.json()["dimensions"][0]["key"] == "values_growth"
    assert "不进入岗位匹配分" in listed.json()["note"]


async def test_dimension_cannot_reference_foreign_evidence(client):
    owner = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "evidence-owner", "content": "我用 Python 做过项目。"},
    )
    evidence_id = owner.json()["items"][0]["id"]
    response = await client.put(
        "/api/v1/profiles/other-user/dimensions",
        json={"user_id": "other-user", "key": "k", "label": "K", "enabled": True,
              "value": {"x": 1}, "evidence_ids": [evidence_id]},
    )
    assert response.status_code == 422


async def test_constraints_are_self_reported(client):
    user_id = "constraint-user"
    response = await client.put(
        "/api/v1/constraints/me",
        json={"user_id": user_id, "kind": "location", "value": "只考虑本地或远程", "strength": 4},
    )
    assert response.status_code == 200
    listed = await client.get("/api/v1/constraints/me", params={"user_id": user_id})
    assert listed.status_code == 200
    assert listed.json()[0]["kind"] == "location"


async def test_new_tables_are_exported_and_deleted(session_factory):
    user_id = "assess-privacy"
    async with session_factory() as session:
        session.add_all([
            AssessmentResult(
                id="ar1", user_id=user_id, instrument="riasec", version="v1",
                result_json={"scores": [["I", 5]]}, answers_json={"I": 5}, consent=True,
            ),
            UserConstraint(id="uc1", user_id=user_id, kind="location", value="remote"),
            DimensionDefinition(
                id="dd1", user_id=user_id, key="values", label="价值观", enabled=True,
            ),
            ProfileExtension(
                id="pe1", user_id=user_id, dimension_key="values",
                value_json={"priority": "growth"},
            ),
        ])
        await session.commit()
        principal = Principal(
            user_id=user_id, token_id=None,
            scopes=("read", "write", "export", "delete", "manage"),
        )
        exported = await export_user_data(session, principal=principal)
        assert len(exported["assessments"]) == 1
        assert len(exported["constraints"]) == 1
        assert len(exported["dimensions"]) == 1
        assert len(exported["profile_extensions"]) == 1

        deleted = await delete_user_account(session, principal=principal)
        assert deleted["deleted_counts"]["assessment_results"] == 1
        assert deleted["deleted_counts"]["user_constraints"] == 1
        assert deleted["deleted_counts"]["dimension_definitions"] == 1
        assert deleted["deleted_counts"]["profile_extensions"] == 1
        assert await session.get(AssessmentResult, "ar1") is None
        assert await session.get(ProfileExtension, "pe1") is None


async def test_assessment_changes_mark_existing_reports_stale(session_factory):
    """Submitting or deleting a self-report must invalidate old reports, not facts."""
    user_id = "assess-stale"
    async with session_factory() as session:
        session.add(CareerReport(
            id="rep1", user_id=user_id, job_analysis_id="job1", version=1,
            title="旧报告", content={}, markdown="# 旧报告", is_stale=False,
        ))
        await session.commit()
        await mark_reports_stale(session, user_id)
        await session.commit()
        report = await session.get(CareerReport, "rep1")
    assert report is not None
    assert report.is_stale is True
