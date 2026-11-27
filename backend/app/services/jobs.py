from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.profile import ProfileItem
from app.runtime.store import check_write_scope, read_scope
from app.schemas.job import MatchCoverage
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
        if item.category != "skill" or (
            isinstance(item.details, dict)
            and item.details.get("strength_method") == "unreviewed_quote_candidate_v1"
            and item.details.get("source") != "confirmed_user_update"
        ):
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
    earned: dict[str, float] = {}
    possible: dict[str, float] = {}
    for requirement in requirements:
        if requirement.get("category", "skill") != "skill":
            continue
        weight = 1.0 if requirement["priority"] == "required" else 0.5
        group = requirement.get("alternative_group") or requirement["name"].casefold()
        possible[group] = max(possible.get(group, 0), weight)
        skill = skills.get(requirement["name"].casefold())
        if skill is None:
            matches.append({**requirement, "status": "gap", "evidence_ids": []})
            continue
        item, evidence_ids = skill
        status = classify_match(item.level, evidence_ids)
        contribution = weight * (1.0 if status == "strong" else 0.65)
        earned[group] = max(earned.get(group, 0), contribution)
        matches.append({
            **requirement, "status": status, "level": item.level,
            "confidence": item.confidence, "evidence_ids": evidence_ids,
        })
    score = round(100 * sum(earned.values()) / sum(possible.values()), 1) if possible else 0.0
    return matches, score


def job_analysis_is_current(
    analysis: JobAnalysis, profile: list[ProfileItem], valid_ids: set[str]
) -> bool:
    if analysis.privacy_redacted or analysis.report.get("match_method") != (
        "weighted_requirements_v2"
    ):
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
    generation = await read_scope(session, user_id)
    profile, valid_ids = await job_inputs(session, user_id)
    requirements, extraction = await extract_requirements_with_fallback(jd_text)
    values = prepare_analysis(
        profile, valid_ids, title, jd_text, weekly_hours, requirements, extraction
    )
    await check_write_scope(session, user_id, expected=generation)
    analysis = await persist_analysis(session, user_id, values)
    await session.commit()
    await session.refresh(analysis)
    return analysis


async def job_inputs(session: AsyncSession, user_id: str) -> tuple[list[ProfileItem], set[str]]:
    profile = await read_profile(session, user_id)
    if not profile:
        raise ValueError("Build the user profile before analyzing a job")
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
    return profile, valid_ids


def prepare_analysis(
    profile: list[ProfileItem], valid_ids: set[str], title: str, jd_text: str, weekly_hours: int,
    requirements: list[dict], extraction: dict,
) -> dict:
    matches, score = match_requirements(requirements, profile, valid_ids)
    if not matches:
        raise ValueError("No scorable skills were identified in this JD; check extraction coverage")
    supported_alternatives = {
        item["alternative_group"] for item in matches
        if item.get("alternative_group") and item["status"] == "strong"
    }
    effective_matches = [
        item for item in matches if item["status"] == "strong"
        or item.get("alternative_group") not in supported_alternatives
    ]
    gaps = [item for item in effective_matches if item["status"] == "gap"]
    required_gaps = [item for item in gaps if item["priority"] == "required"]
    learning_path = build_learning_path(effective_matches, title=title, weekly_hours=weekly_hours)
    strengths = [item for item in matches if item["status"] in {"strong", "partial"}]
    qualifications = [
        {"requirement_id": row["id"], "name": row["name"], "status": "unknown"}
        for row in requirements
        if row.get("category") == "qualification" and row["priority"] == "required"
    ]
    groups = {row.get("alternative_group") or row["name"] for row in matches}
    assessed = {row.get("alternative_group") or row["name"] for row in strengths}
    if qualifications:
        recommendation = "先核对必需资格，再结合能力证据判断是否投递"
    elif required_gaps:
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
        "match_coverage": MatchCoverage(
            assessed_groups=len(assessed), total_skill_groups=len(groups),
            coverage=round(len(assessed) / len(groups), 4), qualification_checks=qualifications,
        ).model_dump(),
        "required_gap_count": len(required_gaps),
        "weekly_hours": weekly_hours,
        "learning_path_method": "required_first_v2",
    }
    return {
        "title": title, "jd_text": jd_text, "score": score, "requirements": requirements,
        "matches": matches, "gaps": gaps, "learning_path": learning_path, "report": report,
    }


async def persist_analysis(session: AsyncSession, user_id: str, values: dict) -> JobAnalysis:
    analysis = JobAnalysis(user_id=user_id, **values)
    session.add(analysis)
    await session.flush()
    return analysis
