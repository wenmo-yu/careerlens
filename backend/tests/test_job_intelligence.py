from app.graph import career
from app.models.evidence import Evidence
from app.profile.extractor import extract_profile_items
from app.services import reports
from app.services.job_requirements import extract_requirements, extract_requirements_with_fallback
from app.services.jobs import match_requirements
from app.services.learning_path import build_learning_path


class StubProvider:
    def __init__(self, result: dict | Exception):
        self.result = result

    @property
    def diagnostics(self) -> dict:
        return {"provider": "stub", "model": "structured-test"}

    async def generate_json(self, **_: dict) -> dict:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_negated_skill_and_requirement_are_not_counted():
    records = [
        Evidence(
            id="negative-skill",
            user_id="test-user",
            source_type="benchmark",
            source_name="negative",
            content="尚未掌握 Docker，目前只在了解概念。使用 Python 完成数据清洗。",
            chunk_index=0,
            source_metadata={},
        )
    ]
    names = {item["name"] for item in extract_profile_items(records)}
    assert "Docker" not in names
    assert "Python" in names
    requirements = extract_requirements("不要求 Docker；要求 Python 和 FastAPI。")
    assert {item["name"] for item in requirements} == {"Python", "FastAPI"}


async def test_model_quote_cannot_validate_a_negated_requirement():
    provider = StubProvider(
        {"requirements": [{"name": "Docker", "priority": "required", "quote": "不要求 Docker"}]}
    )
    requirements, diagnostics = await extract_requirements_with_fallback(
        "不要求 Docker；要求 Python。", provider
    )
    assert {item["name"] for item in requirements} == {"Python"}
    assert diagnostics["accepted"] == 0


async def test_jd_model_adds_only_requirements_with_literal_quotes():
    jd = "需要 Python 和 Redis；Kubernetes 项目经验优先。"
    provider = StubProvider(
        {
            "requirements": [
                {"name": "Redis", "priority": "required", "quote": "Redis"},
                {
                    "name": "k8s",
                    "priority": "preferred",
                    "quote": "Kubernetes 项目经验优先",
                },
                {"name": "Go", "priority": "required", "quote": "Go 开发经验"},
            ]
        }
    )
    requirements, diagnostics = await extract_requirements_with_fallback(jd, provider)
    by_name = {item["name"]: item for item in requirements}
    assert "Redis" in by_name
    assert "Go" not in by_name
    assert by_name["Kubernetes"]["priority"] == "preferred"
    assert diagnostics["accepted"] == 2


async def test_jd_model_failure_keeps_reproducible_catalog_rules():
    requirements, diagnostics = await extract_requirements_with_fallback(
        "要求 Python 和 Docker。", StubProvider(RuntimeError("provider unavailable"))
    )
    assert {item["name"] for item in requirements} == {"Python", "Docker"}
    assert diagnostics["method"] == "catalog_rules"
    assert diagnostics["fallback_reason"] == "RuntimeError"


def test_learning_path_uses_level_priority_time_and_goal():
    matches = [
        {
            "name": "Docker",
            "priority": "required",
            "status": "partial",
            "level": 2,
            "evidence_ids": ["e1"],
        },
        {"name": "MCP", "priority": "preferred", "status": "gap", "evidence_ids": []},
        {"name": "Kubernetes", "priority": "required", "status": "gap", "evidence_ids": []},
    ]
    path = build_learning_path(matches, title="Agent 开发实习生", weekly_hours=6)
    assert [item["skill"] for item in path] == ["Kubernetes", "Docker", "MCP"]
    assert path[0]["weeks"] == 3
    assert path[1]["start_week"] == 4
    assert path[1]["current_level"] == 2
    assert path[1]["source_evidence_ids"] == ["e1"]
    assert path[2]["start_week"] == 6
    assert all(item["weeks"] * 6 >= item["estimated_hours"] for item in path)
    assert "Agent 开发实习生" in path[0]["goal"]
    assert "部署" in path[0]["goal"]


def test_jd_priority_stays_in_its_clause_or_explicit_section():
    jd = (
        "要求 Python、LangGraph、Kubernetes，Docker 经验优先。"
        "\nPreferred:\n- Next.js\nRequired:\n- SQL"
    )
    by_name = {item["name"]: item["priority"] for item in extract_requirements(jd)}
    assert by_name == {
        "Python": "required", "LangGraph": "required", "Kubernetes": "required",
        "Docker": "preferred", "Next.js": "preferred", "SQL": "required",
    }


async def test_model_cannot_reweight_catalogued_requirement_with_an_ambiguous_quote():
    provider = StubProvider({
        "requirements": [
            {"name": "Python", "priority": "preferred", "quote": "Python，Docker 优先"},
            {"name": "Redis", "priority": "required", "quote": "不要求 Redis"},
        ],
    })
    requirements, _ = await extract_requirements_with_fallback(
        "需要 Python，Docker 优先；不要求 Redis。", provider
    )
    assert {item["name"]: item["priority"] for item in requirements} == {
        "Python": "required", "Docker": "preferred",
    }


async def test_job_alternatives_are_one_group_and_requirements_point_to_original_spans():
    from app.models.profile import ProfileItem
    from app.services.jobs import prepare_analysis

    jd = "本科及以上；Java 或 Go 二选一；负责协调团队上线。"
    requirements, diagnostics = await extract_requirements_with_fallback(jd, StubProvider({
        "requirements": [
            {"name": "Java", "priority": "required", "quote": "Java 或 Go 二选一"},
            {"name": "Go", "priority": "required", "quote": "Java 或 Go 二选一"},
            {
                "name": "学历", "category": "qualification",
                "priority": "required", "quote": "本科及以上",
            },
            {
                "name": "部署", "category": "responsibility",
                "priority": "required", "quote": "负责协调团队上线",
            },
        ],
    }))
    assert all(
        jd[item["span_start"]:item["span_end"]] == item["raw_quote"] for item in requirements
    )
    profile = [ProfileItem(name="Java", category="skill", level=3, evidence_ids=["java"])]
    result = prepare_analysis(profile, {"java"}, "Platform", jd, 10, requirements, diagnostics)
    assert result["score"] == 100 and result["gaps"] == []
    coverage = result["report"]["match_coverage"]
    assert coverage["total_skill_groups"] == 1 and coverage["coverage"] == 1.0
    assert coverage["qualification_checks"][0]["status"] == "unknown"
    assert "资格" in result["report"]["recommendation"]


def test_weighted_score_ignores_missing_evidence_and_resolves_aliases():
    from app.models.profile import ProfileItem

    requirements = [
        {"name": "Python", "priority": "required"},
        {"name": "PostgreSQL", "priority": "preferred"},
        {"name": "Docker", "priority": "required"},
    ]
    profile = [
        ProfileItem(name="Python", category="skill", level=3, confidence=0.9, evidence_ids=["p"]),
        ProfileItem(name="Postgres", category="skill", level=2, confidence=0.8, evidence_ids=["q"]),
        ProfileItem(name="PostgreSQL", category="skill", level=5, confidence=1, evidence_ids=["x"]),
        ProfileItem(name="Docker", category="skill", level=5, confidence=1, evidence_ids=["y"]),
    ]
    matches, score = match_requirements(requirements, profile, {"p", "q"})
    assert [item["status"] for item in matches] == ["strong", "partial", "gap"]
    assert matches[1]["evidence_ids"] == ["q"]
    assert score == 53.0


async def test_deleted_evidence_blocks_reuse_of_job_analysis(client):
    user_id = "job-freshness"
    user = {"user_id": user_id}
    imported = await client.post(
        "/api/v1/evidence/text", json={**user, "content": "Built Python tools."}
    )
    await client.post("/api/v1/evidence/text", json={**user, "content": "Built Docker containers."})
    assert (await client.post(f"/api/v1/profiles/{user_id}/rebuild")).status_code == 200
    analysis = await client.post(
        "/api/v1/jobs/analyze",
        json={**user, "title": "Backend", "jd_text": "Python and Docker required."},
    )
    assert analysis.status_code == 200
    analysis_id = analysis.json()["id"]
    assert (await client.delete(f"/api/v1/evidence/{imported.json()['items'][0]['id']}")).is_success
    report = await client.post("/api/v1/reports", json={**user, "job_analysis_id": analysis_id})
    assert report.status_code == 409
    reply = await client.post(
        "/api/v1/chat", json={**user, "job_analysis_id": analysis_id, "message": "我还差什么？"}
    )
    assert reply.status_code == 409


async def test_copilot_uses_saved_job_analysis_and_keeps_memory_update_confirmed(client):
    imported = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "job-chat-user",
            "source_type": "self_statement",
            "source_name": "sample",
            "content": "使用 Python 和 FastAPI 开发 Agent 应用。",
        },
    )
    assert imported.status_code == 201
    assert (await client.post("/api/v1/profiles/job-chat-user/rebuild")).status_code == 200
    analysis = await client.post(
        "/api/v1/jobs/analyze",
        json={
            "user_id": "job-chat-user",
            "title": "Agent 开发实习生",
            "jd_text": "要求 Python、FastAPI 和 Kubernetes。",
            "weekly_hours": 6,
        },
    )
    assert analysis.status_code == 200
    analysis_id = analysis.json()["id"]

    reply = await client.post(
        "/api/v1/chat",
        json={
            "user_id": "job-chat-user",
            "message": "我还差什么？",
            "job_analysis_id": analysis_id,
        },
    )
    assert reply.status_code == 200
    assert reply.json()["intent"] == "skill_gap"
    assert "Kubernetes" in reply.json()["answer"]
    assert reply.json()["model"]["provider"] == "job_analysis"

    memory = await client.post(
        "/api/v1/chat",
        json={
            "user_id": "job-chat-user",
            "message": "我不再考虑纯 CV 岗位，更希望做 Agent 开发。",
            "thread_id": reply.json()["thread_id"],
        },
    )
    assert memory.status_code == 200
    assert memory.json()["intent"] == "memory_update"
    assert "确认写入" in memory.json()["answer"]
    profile = (await client.get("/api/v1/profiles/job-chat-user")).json()
    assert all(item["name"] != "Agent 开发" for item in profile["items"])

    other_import = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "other-user",
            "source_type": "self_statement",
            "source_name": "sample",
            "content": "使用 Python 完成接口开发。",
        },
    )
    assert other_import.status_code == 201
    assert (await client.post("/api/v1/profiles/other-user/rebuild")).status_code == 200
    another_user = await client.post(
        "/api/v1/chat",
        json={"user_id": "other-user", "message": "还差什么", "job_analysis_id": analysis_id},
    )
    assert another_user.status_code == 404


async def test_chat_rejects_fabricated_inline_evidence_citation(monkeypatch):
    monkeypatch.setattr(
        career,
        "get_llm_provider",
        lambda *a, **k: StubProvider(
            {"answer": "熟悉 Python。[Evidence: fabricated]", "cited_evidence_ids": ["e1"]}
        ),
    )
    result = await career.compose_answer(
        {
            "message": "我有什么优势？",
            "intent": "profile_question",
            "profile": [],
            "retrieved_evidence": [{"evidence_id": "e1", "content": "Python 项目"}],
        }
    )
    assert "fabricated" not in result["answer"]
    assert result["model_diagnostics"]["fallback"] is True


async def test_chat_accepts_only_valid_inline_and_list_citations(monkeypatch):
    monkeypatch.setattr(
        career,
        "get_llm_provider",
        lambda *a, **k: StubProvider(
            {"answer": "完成 Python 项目。[Evidence: e1]", "cited_evidence_ids": ["fake", "e2"]}
        ),
    )
    result = await career.compose_answer(
        {
            "message": "我有什么优势？",
            "intent": "profile_question",
            "profile": [],
            "retrieved_evidence": [
                {"evidence_id": "e1", "content": "Python 项目"},
                {"evidence_id": "e2", "content": "Docker 项目"},
            ],
        }
    )
    assert result["answer"].count("[Evidence: e1]") == 1
    assert "[Evidence: e2]" in result["answer"]
    assert "fake" not in result["answer"]


async def test_report_rejects_fabricated_inline_evidence_citation(monkeypatch):
    monkeypatch.setattr(
        reports,
        "get_llm_provider",
        lambda *a, **k: StubProvider(
            {
                "executive_summary": "项目能力。[Evidence: fabricated]",
                "interview_pitch": "我做过 Python 项目。",
                "action_suggestions": ["继续实践"],
                "cited_evidence_ids": ["e1"],
            }
        ),
    )
    narrative, diagnostics = await reports._generate_narrative(
        {
            "summary": "经规则核验的摘要",
            "target_role": "Agent 工程师",
            "score": 50,
            "actions": ["补充项目证据"],
        },
        {"e1"},
    )
    assert narrative["executive_summary"] == "经规则核验的摘要"
    assert diagnostics["fallback"] is True
