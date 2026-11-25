"""Persistence for self-reported assessment results.

Both the legacy quick form and the versioned item packs go through
``record_assessment`` so consent, staleness and commit semantics cannot drift
between the two entry points. Nothing here writes to the fact profile.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentResult
from app.models.career_report import CareerReport


async def mark_reports_stale(session: AsyncSession, user_id: str) -> int:
    """Mark current career reports stale after a self-report changes.

    Facts and Evidence stay untouched; only the derived report is flagged for
    regeneration. Returns the number of reports changed.
    """
    reports = list(await session.scalars(
        select(CareerReport).where(
            CareerReport.user_id == user_id,
            CareerReport.is_stale.is_(False),
        )
    ))
    for report in reports:
        report.is_stale = True
    return len(reports)


async def record_assessment(
    session: AsyncSession,
    *,
    user_id: str,
    instrument: str,
    version: str,
    result: dict,
    answers: dict[str, int],
) -> AssessmentResult:
    """Store one consented self-report and invalidate stale reports atomically."""
    record = AssessmentResult(
        user_id=user_id,
        instrument=instrument,
        version=version,
        result_json=result,
        answers_json=dict(answers),
        source="self_report",
        consent=True,
    )
    session.add(record)
    await mark_reports_stale(session, user_id)
    await session.commit()
    await session.refresh(record)
    return record


async def delete_assessment_result(
    session: AsyncSession, record: AssessmentResult
) -> None:
    """Delete one result and flag dependent reports stale in the same commit."""
    user_id = record.user_id
    await session.delete(record)
    await mark_reports_stale(session, user_id)
    await session.commit()
