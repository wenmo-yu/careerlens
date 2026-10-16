import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_analysis import JobAnalysis
from app.models.profile import ProfileItem
from app.profile.catalog import SKILL_ALIASES
from app.services.profile import read_profile


def extract_requirements(jd_text: str) -> list[dict]:
    lowered = jd_text.lower()
    requirements: list[dict] = []
    for skill, aliases in SKILL_ALIASES.items():
        match = next(
            (
                re.search(
                    rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])",
                    lowered,
                )
                for alias in aliases
                if re.search(
                    rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])",
                    lowered,
                )
            ),
            None,
        )
        if match is None:
            continue
        position = match.start()
        context = lowered[max(0, position - 20) : match.end() + 20]
        priority = (
            "preferred"
            if any(word in context for word in ("加分", "优先", "preferred", "plus"))
            else "required"
        )
        requirements.append({"name": skill, "priority": priority})
    return requirements


def _learning_path(gaps: list[dict], weekly_hours: int) -> list[dict]:
    path = []
    for index, gap in enumerate(gaps, start=1):
        hours = 8 if gap["priority"] == "preferred" else 16
        weeks = max(1, round(hours / weekly_hours))
        path.append(
            {
                "stage": index,
                "skill": gap["name"],
                "weeks": weeks,
                "goal": f"完成 {gap['name']} 基础学习、一个可演示实践和复盘记录",
                "deliverables": ["学习笔记", "最小实践项目", "可引用的项目 Evidence"],
            }
        )
    return path


async def analyze_job(
    session: AsyncSession,
    *,
    user_id: str,
    title: str,
    jd_text: str,
    weekly_hours: int,
) -> JobAnalysis:
    profile = await read_profile(session, user_id)
    if not profile:
        raise ValueError("Build the user profile before analyzing a job")

    profile_by_name: dict[str, ProfileItem] = {item.name: item for item in profile}
    requirements = extract_requirements(jd_text)
    if not requirements:
        raise ValueError("No supported technical requirements were found in the JD")

    matches: list[dict] = []
    gaps: list[dict] = []
    earned = 0.0
    possible = 0.0
    for requirement in requirements:
        weight = 1.0 if requirement["priority"] == "required" else 0.5
        possible += weight
        profile_item = profile_by_name.get(requirement["name"])
        if profile_item:
            strength = "strong" if profile_item.level >= 3 else "partial"
            factor = 1.0 if strength == "strong" else 0.65
            earned += weight * factor
            matches.append(
                {
                    **requirement,
                    "status": strength,
                    "level": profile_item.level,
                    "confidence": profile_item.confidence,
                    "evidence_ids": profile_item.evidence_ids,
                }
            )
        else:
            gap = {**requirement, "status": "gap", "evidence_ids": []}
            matches.append(gap)
            gaps.append(gap)

    score = round(100 * earned / possible, 1) if possible else 0.0
    learning_path = _learning_path(gaps, weekly_hours)
    strengths = [item for item in matches if item["status"] in {"strong", "partial"}]
    report = {
        "summary": f"当前与 {title} 的可验证匹配度为 {score}%。",
        "strengths": strengths,
        "gaps": gaps,
        "recommendation": (
            "建议重点投递并针对缺口准备" if score >= 70 else "建议先补齐核心缺口后再重点投递"
        ),
        "claim_policy": "所有能力结论均来自 Profile Item 关联的 Evidence；无证据项标记为 gap。",
    }
    analysis = JobAnalysis(
        user_id=user_id,
        title=title,
        jd_text=jd_text,
        score=score,
        requirements=requirements,
        matches=matches,
        gaps=gaps,
        learning_path=learning_path,
        report=report,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis
