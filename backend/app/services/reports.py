import json
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_llm_provider
from app.models.career_report import CareerReport
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.services.citations import validated_citations
from app.services.profile import read_profile


def _safe_inline(value: str) -> str:
    return " ".join(value.replace("#", "").split())


def _deterministic_actions(analysis: JobAnalysis) -> list[str]:
    actions = [
        f"围绕 {_safe_inline(analysis.title)} 准备一版只包含可验证经历的项目介绍。",
        "逐项核对简历能力描述与 Evidence ID，删除无法回溯的泛化结论。",
    ]
    if analysis.gaps:
        actions.append(f"优先补齐 {analysis.gaps[0]['name']}，完成最小项目并沉淀新 Evidence。")
    else:
        actions.append("选择一个真实岗位投递，并用面试反馈继续校准长期画像。")
    return actions


async def _generate_narrative(context: dict[str, Any], allowed_ids: set[str]) -> tuple[dict, dict]:
    provider = get_llm_provider()
    fallback = {
        "executive_summary": context["summary"],
        "interview_pitch": (
            f"我与 {context['target_role']} 的当前可验证匹配度为 {context['score']}%。"
            "我的能力陈述均可回溯到项目或经历证据，同时会明确说明尚未补齐的能力。"
        ),
        "action_suggestions": context["actions"],
        "cited_evidence_ids": sorted(allowed_ids),
    }
    diagnostics = provider.diagnostics
    if diagnostics["provider"] == "demo":
        return fallback, diagnostics
    schema = {
        "type": "object",
        "required": [
            "executive_summary",
            "interview_pitch",
            "action_suggestions",
            "cited_evidence_ids",
        ],
        "properties": {
            "executive_summary": {"type": "string"},
            "interview_pitch": {"type": "string"},
            "action_suggestions": {"type": "array", "items": {"type": "string"}},
            "cited_evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
    }
    try:
        generated = await provider.generate_json(
            system_prompt=(
                "你是证据优先的职业报告编辑。只可改写已给事实，不得新增经历、技能或证据。"
                "缺口必须保留；行动建议必须可执行。"
            ),
            user_prompt=json.dumps(context, ensure_ascii=False),
            schema=schema,
            operation="career_report",
        )
        summary = str(generated["executive_summary"]).strip()
        pitch = str(generated["interview_pitch"]).strip()
        actions = [
            str(item).strip()
            for item in generated.get("action_suggestions", [])
            if str(item).strip()
        ]
        if not summary or not pitch:
            raise ValueError("Model report narrative is empty")
        cited = validated_citations(
            [summary, pitch, *actions], generated.get("cited_evidence_ids", []), allowed_ids
        )
        return {
            "executive_summary": summary,
            "interview_pitch": pitch,
            "action_suggestions": actions or fallback["action_suggestions"],
            "cited_evidence_ids": cited,
        }, diagnostics
    except Exception as exc:
        return fallback, {**diagnostics, "fallback": True, "reason": type(exc).__name__}


def _render_markdown(title: str, version: int, content: dict[str, Any]) -> str:
    profile = content["profile"]
    capabilities = content["core_capabilities"]
    evidence = content["evidence_catalog"]
    matches = content["job_matching"]
    gaps = content["skill_gaps"]
    path = content["learning_path"]
    actions = content["action_plan"]

    lines = [
        f"# {_safe_inline(title)}",
        "",
        f"> CareerLens Report v{version} · Evidence-grounded",
        "",
        content["executive_summary"],
        "",
        "## 01 个人职业画像",
        "",
    ]
    for category, names in profile.items():
        lines.append(f"- **{category}**：{'、'.join(names)}")
    lines.extend(["", "## 02 核心能力", ""])
    for item in capabilities:
        ids = "、".join(item["evidence_ids"])
        lines.append(
            f"- **{item['name']}**：Level {item['level']} / "
            f"置信度 {item['confidence']:.0%} / Evidence {ids}"
        )
    lines.extend(["", "## 03 项目与经历证据", ""])
    for item in evidence:
        lines.append(
            f"- `{item['id']}` · {item['source_type']} · {_safe_inline(item['source_name'])}"
        )
    lines.extend(
        [
            "",
            "## 04 推荐就业方向",
            "",
            f"- 目标方向：**{content['career_direction']['primary_role']}**",
            f"- 当前可验证匹配度：**{content['career_direction']['match_score']}%**",
            "",
            "## 05 目标岗位匹配",
            "",
        ]
    )
    for item in matches:
        ids = "、".join(item["evidence_ids"]) or "暂无"
        lines.append(f"- **{item['name']}**：{item['status']}（Evidence：{ids}）")
    lines.extend(["", "## 06 当前能力缺口", ""])
    lines.extend([f"- **{item['name']}**：{item['priority']}，暂无直接证据" for item in gaps])
    if not gaps:
        lines.append("- 当前 JD 未识别到明确能力缺口。")
    lines.extend(["", "## 07 个性化学习路线", ""])
    for item in path:
        lines.append(
            f"{item['stage']}. **{item['skill']}**（预计 {item['weeks']} 周）："
            f"{item['goal']}"
        )
    if not path:
        lines.append("- 维持项目实践，并用新的岗位反馈持续更新画像。")
    lines.extend(["", "## 08 求职行动建议", ""])
    lines.extend([f"- {item}" for item in actions])
    lines.extend(["", "### 面试表达", "", content["interview_pitch"], ""])
    return "\n".join(lines)


async def generate_report(
    session: AsyncSession, *, user_id: str, job_analysis_id: str
) -> CareerReport:
    analysis = await session.get(JobAnalysis, job_analysis_id)
    if analysis is None or analysis.user_id != user_id:
        raise ValueError("Job analysis not found for this user")
    profile = await read_profile(session, user_id)
    if not profile:
        raise ValueError("Build the user profile before generating a report")

    referenced_ids = sorted({value for item in profile for value in item.evidence_ids})
    evidence_records = list(
        await session.scalars(
            select(Evidence).where(Evidence.user_id == user_id, Evidence.id.in_(referenced_ids))
        )
    )
    evidence_by_id = {item.id: item for item in evidence_records}
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in profile:
        grouped[item.category].append(item.name)

    actions = _deterministic_actions(analysis)
    context = {
        "target_role": analysis.title,
        "score": analysis.score,
        "summary": analysis.report["summary"],
        "skills": [item.name for item in profile if item.category == "skill"],
        "matches": analysis.matches,
        "gaps": analysis.gaps,
        "learning_path": analysis.learning_path,
        "actions": actions,
        "evidence_ids": referenced_ids,
    }
    narrative, diagnostics = await _generate_narrative(context, set(referenced_ids))
    content = {
        "profile": dict(grouped),
        "core_capabilities": [
            {
                "name": item.name,
                "category": item.category,
                "level": item.level,
                "confidence": item.confidence,
                "evidence_ids": item.evidence_ids,
            }
            for item in profile
            if item.category in {"skill", "role"}
        ],
        "evidence_catalog": [
            {
                "id": evidence_id,
                "source_type": evidence_by_id[evidence_id].source_type,
                "source_name": evidence_by_id[evidence_id].source_name,
            }
            for evidence_id in referenced_ids
            if evidence_id in evidence_by_id
        ],
        "career_direction": {
            "primary_role": analysis.title,
            "match_score": analysis.score,
            "recommendation": analysis.report["recommendation"],
        },
        "job_matching": analysis.matches,
        "skill_gaps": analysis.gaps,
        "learning_path": analysis.learning_path,
        "action_plan": narrative["action_suggestions"],
        "executive_summary": narrative["executive_summary"],
        "interview_pitch": narrative["interview_pitch"],
        "referenced_evidence_ids": narrative["cited_evidence_ids"],
        "claim_policy": analysis.report["claim_policy"],
    }
    latest_version = await session.scalar(
        select(func.max(CareerReport.version)).where(CareerReport.user_id == user_id)
    )
    version = int(latest_version or 0) + 1
    title = f"{analysis.title} · 个人职业报告"
    record = CareerReport(
        user_id=user_id,
        job_analysis_id=analysis.id,
        version=version,
        title=title,
        content=content,
        markdown=_render_markdown(title, version, content),
        model_diagnostics=diagnostics,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def list_reports(
    session: AsyncSession, *, user_id: str, limit: int = 20
) -> list[CareerReport]:
    result = await session.scalars(
        select(CareerReport)
        .where(CareerReport.user_id == user_id)
        .order_by(CareerReport.created_at.desc(), CareerReport.version.desc())
        .limit(limit)
    )
    return list(result)
