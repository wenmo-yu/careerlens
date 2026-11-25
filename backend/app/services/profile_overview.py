"""HY4-B: explainable read-only profile overview and agent manifest."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentResult
from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.models.source_document import SourceDocument
from app.schemas.profile_overview import (
    AssessmentHighlight,
    CoverageRead,
    ProfileOverviewRead,
)

WEAK_CONFIDENCE = 0.7


async def build_profile_overview(session: AsyncSession, user_id: str) -> ProfileOverviewRead:
    """Aggregate what is actually stored. This derives no new user facts."""
    evidence = list(
        await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
    )
    evidence_ids = {record.id for record in evidence}
    documents = list(
        await session.scalars(select(SourceDocument).where(SourceDocument.user_id == user_id))
    )
    items = list(
        await session.scalars(select(ProfileItem).where(ProfileItem.user_id == user_id))
    )

    coverage = CoverageRead()
    by_category: dict[str, int] = {}
    confirmed = 0
    self_report = 0
    for item in items:
        by_category[item.category] = by_category.get(item.category, 0) + 1
        details = item.details or {}
        if details.get("source") == "confirmed_user_update":
            confirmed += 1
        elif details.get("source") == "self_report":
            self_report += 1
        valid = [eid for eid in (item.evidence_ids or []) if eid in evidence_ids]
        if not valid:
            coverage.missing += 1
        elif len(valid) == 1 or item.confidence < WEAK_CONFIDENCE:
            coverage.weak += 1
        else:
            coverage.supported += 1

    readable = sum(
        1 for record in evidence
        if record.content.strip() and not (record.source_metadata or {}).get("ocr_pending")
    )
    latest_assessment: dict[str, AssessmentHighlight] = {}
    for record in await session.scalars(
        select(AssessmentResult)
        .where(AssessmentResult.user_id == user_id)
        .order_by(AssessmentResult.taken_at.desc())
    ):
        if record.instrument in latest_assessment:
            continue
        result = record.result_json or {}
        latest_assessment[record.instrument] = AssessmentHighlight(
            instrument=record.instrument,
            title=result.get("instrument_title"),
            version=record.version,
            code=result.get("code"),
            taken_at=record.taken_at,
        )
    return ProfileOverviewRead(
        user_id=user_id,
        evidence_count=len(evidence),
        source_document_count=len(documents),
        readable_evidence_count=readable,
        profile_item_count=len(items),
        confirmed_item_count=confirmed,
        unconfirmed_item_count=len(items) - confirmed,
        self_report_item_count=self_report,
        coverage=coverage,
        by_category=by_category,
        assessments=sorted(latest_assessment.values(), key=lambda row: row.instrument),
        generated_at=datetime.now(UTC),
    )


def build_agent_manifest(user_id: str, overview: ProfileOverviewRead) -> dict:
    """Machine-readable capability list for AI clients.

    Agent may read facts and propose drafts; it can never silently write a
    long-term profile. Writes still go through the human-in-the-loop proposal
    and decision endpoints.
    """
    return {
        "schema_version": "1.0",
        "user_id": user_id,
        "profile_version": overview.generated_at.isoformat(),
        "coverage": overview.coverage.model_dump(),
        "active_dimensions": sorted(overview.by_category),
        "enabled_dimensions": sorted(overview.by_category) + ["evidence_health"],
        "capabilities": [
            {
                "name": "query_profile",
                "endpoint": "GET /profiles/{user_id}",
                "requires_scope": "read",
                "evidence_policy": "facts_only",
            },
            {
                "name": "query_profile_overview",
                "endpoint": "GET /profiles/{user_id}/overview",
                "requires_scope": "read",
                "evidence_policy": "derived_read_only",
            },
            {
                "name": "query_evidence",
                "endpoint": "GET /evidence?user_id=...",
                "requires_scope": "read",
                "evidence_policy": "facts_only",
            },
            {
                "name": "propose_profile_update",
                "endpoint": "POST /profiles/{user_id}/proposals",
                "requires_scope": "write",
                "evidence_policy": "draft_only",
            },
            {
                "name": "analyze_job",
                "endpoint": "POST /jobs/analyze",
                "requires_scope": "write",
                "evidence_policy": "facts_only",
            },
        ],
        "writable_policy": "agent_can_propose_only",
        "notes": [
            "ProfileItem.id is rewritten on rebuild; use (category, name) "
            "plus evidence_ids as the stable reference.",
            "Interaction signals (claim_strength=preference_signal) must not be "
            "promoted to skill/experience/target_role.",
            "Assessment results are self-reported and are not part of the fact "
            "profile or match score.",
        ],
    }
