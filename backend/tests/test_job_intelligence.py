from app.graph import career
from app.models.evidence import Evidence
from app.profile.extractor import extract_profile_items
from app.services import reports
from app.services.job_requirements import extract_requirements, extract_requirements_with_fallback
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
    assert [item["skill"] for item in path] == ["Kubernetes", "MCP", "Docker"]
    assert path[0]["weeks"] == 3
    assert path[1]["start_week"] == 4
    assert path[2]["current_level"] == 2
    assert path[2]["source_evidence_ids"] == ["e1"]
    assert "Agent 开发实习生" in path[0]["goal"]
    assert "部署" in path[0]["goal"]


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
        lambda: StubProvider(
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
        lambda: StubProvider(
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
        lambda: StubProvider(
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
