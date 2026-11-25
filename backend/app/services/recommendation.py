"""HY4-C: deterministic, traceable role and course recommendations.

No network calls, no market data, no personality scores. Every recommendation
is derived from the user's real skill items and still-present Evidence IDs.
"""

from app.catalog.loader import load_courses, load_roles
from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.services.learning_path import build_learning_path


def _normalise(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def recommend_roles(
    items: list[ProfileItem], evidence: list[Evidence], limit: int = 5,
) -> list[dict]:
    """Score role templates by overlap with the user's evidenced skills.

    Self-reported assessment answers and interaction signals never enter the
    score: only skill ProfileItems whose evidence IDs are still live.
    """
    live_ids = {record.id for record in evidence}
    skills = {
        _normalise(item.name): item
        for item in items
        if item.category == "skill"
        and item.evidence_ids
        and any(eid in live_ids for eid in item.evidence_ids)
    }
    rows = []
    for role in load_roles():
        required = [_normalise(name) for name in role["required_skills"]]
        nice = [_normalise(name) for name in role["nice_to_have"]]
        matched = [name for name in required if name in skills]
        nice_matched = [name for name in nice if name in skills]
        gaps = [name for name in required if name not in skills]
        if not matched and not nice_matched:
            continue
        evidence_ids = sorted({
            eid
            for name in matched + nice_matched
            for eid in skills[name].evidence_ids
            if eid in live_ids
        })
        rows.append({
            "role_id": role["role_id"],
            "name": role["name"],
            "family": role["family"],
            "matched_required": matched,
            "matched_nice_to_have": nice_matched,
            "gaps": gaps,
            "evidence_ids": evidence_ids,
            "reason": (
                f"已覆盖 {len(matched)}/{len(required)} 项必需技能，"
                f"{len(nice_matched)} 项加分技能，可回查 {len(evidence_ids)} 条证据。"
            ),
            "typical_tasks": role["typical_tasks"],
            "growth_path": role["growth_path"],
            "source_note": role["source_note"],
            "coverage": round(len(matched) / max(1, len(required)), 3),
        })
    rows.sort(key=lambda row: (-row["coverage"], -len(row["matched_nice_to_have"]), row["role_id"]))
    return rows[: max(1, min(limit, 10))]


def recommend_courses(
    skill: str, level: str | None = None, weekly_hours: int = 8, limit: int = 6,
) -> list[dict]:
    """Pick local courses for one skill, respecting prerequisites and budget.

    This only returns catalog metadata and URLs; it never fetches the URL.
    """
    target = _normalise(skill)
    candidates = [row for row in load_courses() if _normalise(row["skill"]) == target]
    if level:
        preferred = [row for row in candidates if row["level"] == level]
        if preferred:
            candidates = preferred
    candidates.sort(key=lambda row: (row["estimated_hours"], row["course_id"]))
    chosen: list[dict] = []
    spent = 0
    for row in candidates:
        hours = row["estimated_hours"]
        if spent and spent + hours > max(1, weekly_hours) * 2:
            continue
        chosen.append({**row, "prerequisite_note": (
            "需先完成：" + "、".join(row["prerequisites"]) if row["prerequisites"] else "无先修要求"
        )})
        spent += hours
        if len(chosen) >= max(1, min(limit, 12)):
            break
    return chosen


def build_learning_plan_v2(
    existing_path: list[dict], items: list[ProfileItem], live_evidence_ids: set[str],
) -> list[dict]:
    """Enrich the existing deterministic path without changing its ordering."""
    levels = {
        _normalise(item.name): item.level
        for item in items if item.category == "skill"
    }
    result = []
    for step in existing_path:
        skill = step.get("skill", "")
        current = step.get("current_level") or levels.get(_normalise(skill), 1)
        courses = recommend_courses(skill, weekly_hours=max(1, int(step.get("weeks", 1) * 8)))
        result.append({
            **step,
            "target_level": min(5, int(current) + 1),
            "resources": [
                {"course_id": row["course_id"], "title": row["title"], "url": row["url"],
                 "estimated_hours": row["estimated_hours"], "prerequisites": row["prerequisites"]}
                for row in courses[:3]
            ],
            "verification": courses[0]["verification"] if courses else step.get("goal", ""),
            "progress_status": "待开始",
        })
    return result


__all__ = ["recommend_roles", "recommend_courses", "build_learning_plan_v2", "build_learning_path"]
