"""Wake reconciliation for durable schedules (M8 sleep/misfire strategy).

When the scheduler was not running for a while (app closed, machine asleep),
some schedules may have due times inside the gap. This service reconciles them
on the next start using the existing schedule trigger, which already applies
the skip/run_once misfire policy and the (schedule_id, due_at) idempotency key.

This is the strategy layer only: it does not register OS wake timers, does not
run while the app is closed, and does not claim the machine actually slept.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import AgentSchedule
from app.models.wake import AgentWakeReport
from app.runtime.agent import schedule as schedule_service

MAX_RECONCILE = 100


class WakeConflict(ValueError):
    """Invalid reconciliation window."""


def build_window(last_seen: int, now: int) -> tuple[int, int]:
    """Return a valid [last_seen, now] window; reject inverted input."""

    if last_seen < 0 or now < 0 or now < last_seen:
        raise WakeConflict("now must be greater than or equal to last_seen")
    return last_seen, now


async def reconcile(
    session: AsyncSession, *, last_seen: int, now: int, limit: int = MAX_RECONCILE
) -> AgentWakeReport:
    """Reconcile schedules whose due time fell inside the liveness gap [start, end]."""

    start, end = build_window(last_seen, now)
    gap = end - start
    rows = list(
        await session.scalars(
            select(AgentSchedule.id)
            .where(
                AgentSchedule.state == "active",
                AgentSchedule.next_due >= start,
                AgentSchedule.next_due <= end,
            )
            .order_by(AgentSchedule.next_due)
            .limit(limit)
        )
    )
    triggered = 0
    skipped = 0
    for schedule_id in rows:
        record = await session.get(AgentSchedule, schedule_id)
        if record is None:
            continue
        try:
            occurrence = await schedule_service.trigger(
                session, user_id=record.user_id, schedule_id=schedule_id, now=end
            )
        except schedule_service.ScheduleConflict:
            continue
        if occurrence is None:
            continue
        if occurrence.status == "skipped":
            skipped += 1
        elif occurrence.status in ("claimed", "succeeded"):
            triggered += 1
    report = AgentWakeReport(
        observed_gap_seconds=gap,
        missed_due=len(rows),
        triggered=triggered,
        skipped=skipped,
        reason="wake_reconcile",
    )
    session.add(report)
    await session.flush()
    return report


async def list_reports(session: AsyncSession, *, limit: int = 50) -> list[AgentWakeReport]:
    return list(
        await session.scalars(
            select(AgentWakeReport).order_by(AgentWakeReport.created_at.desc()).limit(limit)
        )
    )
