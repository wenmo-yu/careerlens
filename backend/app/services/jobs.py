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


def classify_match(level: int, evidence_ids: list[str]) -> str:
    if not evidence_ids:
        return "gap"
    return "strong" if level >= 3 else "partial"


def match_requirements(
    requirements: list[dict], profile: list[ProfileItem], valid_ids: set[str]
) -> tuple[list[dict], float]:
    skills: dict[str, tuple[ProfileItem, list[str]]] = {}
    for item in profile:
        if item.category != "skill":
            continue
        name = normalize_skill(item.name).casefold()
        evidence_ids = sorted(set(item.evidence_ids) & valid_ids)
        previous = skills.get(name)
        if evidence_ids and (
            previous is None
            or (item.level, item.confidence) > (previous[0].level, previous[0].confidence)
        ):
            skills[name] = item, evidence_ids

    matches: list[dict] = []
    earned = 0.0
    possible = 0.0
    for requirement in requirements:
        weight = 1.0 if requirement["priority"] == "required" else 0.5
        possible += weight
        skill = skills.get(requirement["name"].casefold())
        if skill is None:
            matches.append({**requirement, "status": "gap", "evidence_ids": []})
            continue
        item, evidence_ids = skill
        status = classify_match(item.level, evidence_ids)
        earned += weight * (1.0 if status == "strong" else 0.65)
        matches.append({
            **requirement, "status": status, "level": item.level,
            "confidence": item.confidence, "evidence_ids": evidence_ids,
        })
    return matches, round(100 * earned / possible, 1) if possible else 0.0


def job_analysis_is_current(
    analysis: JobAnalysis, profile: list[ProfileItem], valid_ids: set[str]
) -> bool:
    if analysis.report.get("match_method") != "weighted_requirements_v2":
        return False
    matches, score = match_requirements(analysis.requirements, profile, valid_ids)
    return analysis.matches == matches and analysis.score == score


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

    matches, score = match_requirements(requirements, profile, valid_ids)
    gaps = [item for item in matches if item["status"] == "gap"]
    required_gaps = [item for item in gaps if item["priority"] == "required"]
    learning_path = build_learning_path(matches, title=title, weekly_hours=weekly_hours)
    strengths = [item for item in matches if item["status"] in {"strong", "partial"}]
    if required_gaps:
        recommendation = f"先补齐 {len(required_gaps)} 项必需能力缺口，再判断是否重点投递"
    elif score >= 70:
        recommendation = "建议重点投递并针对缺口准备"
    else:
        recommendation = "建议先加强已有能力的证据，再重点投递"
    report = {
        "summary": f"按当前规则计算，与 {title} 的证据支持匹配分为 {score}%；这不是录用概率。",
        "strengths": strengths,
        "gaps": gaps,
        "recommendation": recommendation,
        "claim_policy": "所有能力结论均来自 Profile Item 关联的 Evidence；无证据项标记为 gap。",
        "requirement_extraction": extraction,
        "match_method": "weighted_requirements_v2",
        "required_gap_count": len(required_gaps),
        "weekly_hours": weekly_hours,
        "learning_path_method": "required_first_v2",
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
