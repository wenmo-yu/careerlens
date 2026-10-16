from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.profile import ProfileItem
from app.services.job_requirements import (
    extract_requirements_with_fallback,
    normalize_skill,
)
from app.services.learning_path import build_learning_path
from app.services.profile import read_profile


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

    profile_by_name: dict[str, ProfileItem] = {
        normalize_skill(item.name).casefold(): item for item in profile if item.category == "skill"
    }
    requirements, extraction = await extract_requirements_with_fallback(jd_text)
    if not requirements:
        raise ValueError("No supported technical requirements were found in the JD")

    referenced_ids = {evidence_id for item in profile for evidence_id in item.evidence_ids}
    valid_ids = (
        set(
            await session.scalars(
                select(Evidence.id).where(
                    Evidence.user_id == user_id, Evidence.id.in_(referenced_ids)
                )
            )
        )
        if referenced_ids
        else set()
    )

    matches: list[dict] = []
    gaps: list[dict] = []
    earned = 0.0
    possible = 0.0
    for requirement in requirements:
        weight = 1.0 if requirement["priority"] == "required" else 0.5
        possible += weight
        profile_item = profile_by_name.get(requirement["name"].casefold())
        evidence_ids = (
            [item for item in profile_item.evidence_ids if item in valid_ids]
            if profile_item
            else []
        )
        if profile_item and evidence_ids:
            strength = "strong" if profile_item.level >= 3 else "partial"
            factor = 1.0 if strength == "strong" else 0.65
            earned += weight * factor
            matches.append(
                {
                    **requirement,
                    "status": strength,
                    "level": profile_item.level,
                    "confidence": profile_item.confidence,
                    "evidence_ids": evidence_ids,
                }
            )
        else:
            gap = {**requirement, "status": "gap", "evidence_ids": []}
            matches.append(gap)
            gaps.append(gap)

    score = round(100 * earned / possible, 1) if possible else 0.0
    learning_path = build_learning_path(matches, title=title, weekly_hours=weekly_hours)
    strengths = [item for item in matches if item["status"] in {"strong", "partial"}]
    report = {
        "summary": f"按当前规则计算，与 {title} 的证据支持匹配分为 {score}%；这不是录用概率。",
        "strengths": strengths,
        "gaps": gaps,
        "recommendation": (
            "建议重点投递并针对缺口准备" if score >= 70 else "建议先补齐核心缺口后再重点投递"
        ),
        "claim_policy": "所有能力结论均来自 Profile Item 关联的 Evidence；无证据项标记为 gap。",
        "requirement_extraction": extraction,
        "learning_path_method": "bounded_rule_plan",
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
