"""Durable agent schedules with idempotent occurrences (M8).

Schedules are internal planners. They submit a normal agent run for the same
user and never perform external actions themselves. A revoked actor token, a
disabled schedule or a duplicate due occurrence stops the trigger.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import AgentSchedule, AgentScheduleOccurrence
from app.runtime.agent import store


class ScheduleConflict(ValueError):
    """Schedule input or state contradicts durable facts."""


def now_seconds() -> int:
    return int(datetime.now(UTC).timestamp())


async def create_schedule(
    session: AsyncSession,
    *,
    user_id: str,
    workspace_id: str,
    name: str,
    prompt: str,
    interval_seconds: int,
    misfire_policy: str = "skip",
    actor_token_id: str | None,
    start_at: int | None = None,
) -> AgentSchedule:
    if not name.strip() or len(name) > 200:
        raise ScheduleConflict("name must contain 1-200 characters")
    if not prompt.strip() or len(prompt) > 20_000:
        raise ScheduleConflict("prompt must contain 1-20000 characters")
    if interval_seconds < 60 or interval_seconds > 30 * 24 * 3600:
        raise ScheduleConflict("interval_seconds must be between 60 and 2592000")
    if misfire_policy not in ("skip", "run_once"):
        raise ScheduleConflict("misfire_policy must be skip or run_once")
    due = start_at or now_seconds()
    record = AgentSchedule(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name.strip(),
        prompt=prompt.strip(),
        interval_seconds=interval_seconds,
        misfire_policy=misfire_policy,
        actor_token_id=actor_token_id,
        next_due=due,
    )
    session.add(record)
    await session.flush()
    return record


async def list_schedules(
    session: AsyncSession, *, user_id: str
) -> list[AgentSchedule]:
    return list(
        await session.scalars(
            select(AgentSchedule)
            .where(AgentSchedule.user_id == user_id)
            .order_by(AgentSchedule.next_due, AgentSchedule.id)
        )
    )


async def set_state(
    session: AsyncSession, *, user_id: str, schedule_id: str, state: str
) -> AgentSchedule | None:
    if state not in ("active", "paused", "disabled"):
        raise ScheduleConflict("state must be active, paused or disabled")
    record = await session.scalar(
        select(AgentSchedule).where(
            AgentSchedule.id == schedule_id, AgentSchedule.user_id == user_id
        )
    )
    if record is None:
        return None
    record.state = state
    await session.flush()
    await session.refresh(record)
    return record


def _advance(due_at: int, interval: int, now: int) -> int:
    if now <= due_at:
        return due_at + interval
    steps = max(1, math.ceil((now - due_at + 1) / interval))
    return due_at + steps * interval


async def trigger(
    session: AsyncSession,
    *,
    user_id: str,
    schedule_id: str,
    now: int | None = None,
    manual: bool = False,
) -> AgentScheduleOccurrence | None:
    """Trigger one due occurrence at most once.

    The unique ``(schedule_id, due_at)`` row is the idempotency key. A revoked
    actor token is recorded as a failed occurrence and pauses the schedule so
    it cannot keep retrying without user consent.
    """

    moment = now if now is not None else now_seconds()
    record = await session.scalar(
        select(AgentSchedule)
        .where(AgentSchedule.id == schedule_id, AgentSchedule.user_id == user_id)
        .with_for_update()
    )
    if record is None:
        return None
    if record.state != "active":
        raise ScheduleConflict("Schedule is not active")
    if not manual and record.next_due > moment:
        return None
    due_at = record.next_due if not manual else moment
    existing = await session.scalar(
        select(AgentScheduleOccurrence).where(
            AgentScheduleOccurrence.schedule_id == record.id,
            AgentScheduleOccurrence.due_at == due_at,
        )
    )
    if existing is not None:
        return existing

    late = moment - due_at
    if late > 2 * record.interval_seconds and record.misfire_policy == "skip":
        occurrence = AgentScheduleOccurrence(
            schedule_id=record.id, user_id=user_id, due_at=due_at,
            status="skipped", reason="misfire_skipped",
        )
        session.add(occurrence)
        if not manual:
            record.next_due = _advance(due_at, record.interval_seconds, moment)
            record.last_occurrence = due_at
        await session.flush()
        return occurrence

    child_session = await store.create_session(
        session,
        user_id=user_id,
        title=f"计划：{record.name[:80]}",
        workspace_id=record.workspace_id,
    )
    request_key = f"schedule:{record.id}:{due_at}"
    run, _created = await store.submit_turn(
        session,
        user_id=user_id,
        session_id=child_session.id,
        text=record.prompt,
        token_id=record.actor_token_id,
        request_key=request_key,
    )
    occurrence = AgentScheduleOccurrence(
        schedule_id=record.id,
        user_id=user_id,
        due_at=due_at,
        status="claimed",
        run_id=run.id,
    )
    session.add(occurrence)
    record.next_due = _advance(due_at, record.interval_seconds, moment)
    record.last_occurrence = due_at
    await session.flush()
    return occurrence


async def trigger_due(
    session: AsyncSession, *, now: int | None = None, limit: int = 20
) -> list[AgentScheduleOccurrence]:
    """Trigger all due active schedules; errors are recorded, not raised."""

    moment = now if now is not None else now_seconds()
    rows = list(
        await session.scalars(
            select(AgentSchedule.id)
            .where(AgentSchedule.state == "active", AgentSchedule.next_due <= moment)
            .order_by(AgentSchedule.next_due)
            .limit(limit)
        )
    )
    occurrences: list[AgentScheduleOccurrence] = []
    for schedule_id in rows:
        try:
            occurrence = await trigger(
                session,
                user_id=(await session.get(AgentSchedule, schedule_id)).user_id,
                schedule_id=schedule_id,
                now=moment,
            )
        except store.RunAccessRevoked:
            record = await session.get(AgentSchedule, schedule_id)
            if record is not None:
                record.state = "paused"
            await session.flush()
            continue
        except ScheduleConflict:
            continue
        if occurrence is not None:
            occurrences.append(occurrence)
    return occurrences


async def list_occurrences(
    session: AsyncSession, *, user_id: str, schedule_id: str
) -> list[AgentScheduleOccurrence]:
    return list(
        await session.scalars(
            select(AgentScheduleOccurrence)
            .where(
                AgentScheduleOccurrence.user_id == user_id,
                AgentScheduleOccurrence.schedule_id == schedule_id,
            )
            .order_by(AgentScheduleOccurrence.due_at.desc())
        )
    )
