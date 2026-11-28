"""In-app notification centre and cross-item search (M8 experience package).

Everything shown is derived from existing durable facts. The only row this
module writes is a read receipt. Nothing is delivered outside the app.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentApproval, AgentSession
from app.models.multi import AgentTask
from app.models.notification import AgentNotificationRead
from app.models.role import AgentRole
from app.models.run import AgentRun
from app.models.schedule import AgentSchedule, AgentScheduleOccurrence

MAX_NOTIFICATIONS = 50
MAX_SEARCH = 30


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def list_notifications(session: AsyncSession, *, user_id: str) -> list[dict]:
    """Derive a bounded inbox from real facts and merge read receipts."""

    read_keys = set(
        await session.scalars(
            select(AgentNotificationRead.fact_key).where(
                AgentNotificationRead.user_id == user_id
            )
        )
    )
    items: list[dict] = []

    pending = await session.scalars(
        select(AgentApproval)
        .where(AgentApproval.user_id == user_id, AgentApproval.status == "pending")
        .order_by(AgentApproval.created_at.desc())
        .limit(MAX_NOTIFICATIONS)
    )
    for row in pending:
        items.append(
            {
                "fact_key": f"approval:{row.id}",
                "kind": "approval_pending",
                "title": "待审批的工具调用",
                "detail": f"工具 {row.tool} 等待你的决定",
                "ref_id": row.id,
                "created_at": _iso(row.created_at),
            }
        )

    failed_runs = await session.scalars(
        select(AgentRun)
        .where(
            AgentRun.user_id == user_id,
            AgentRun.executor_kind == "agent",
            AgentRun.status.in_(("failed", "interrupted", "cancelled")),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(MAX_NOTIFICATIONS)
    )
    for row in failed_runs:
        items.append(
            {
                "fact_key": f"run_failed:{row.id}",
                "kind": "run_failed",
                "title": "一次 Agent 运行未完成",
                "detail": row.error_code or row.status,
                "ref_id": row.id,
                "created_at": _iso(row.created_at),
            }
        )

    failed_tasks = await session.scalars(
        select(AgentTask)
        .where(AgentTask.user_id == user_id, AgentTask.status == "failed")
        .order_by(AgentTask.updated_at.desc())
        .limit(MAX_NOTIFICATIONS)
    )
    for row in failed_tasks:
        items.append(
            {
                "fact_key": f"task_failed:{row.id}",
                "kind": "task_failed",
                "title": "一个子任务失败",
                "detail": row.error or "task failed",
                "ref_id": row.id,
                "created_at": _iso(row.updated_at),
            }
        )

    bad_occurrences = await session.scalars(
        select(AgentScheduleOccurrence)
        .where(
            AgentScheduleOccurrence.user_id == user_id,
            AgentScheduleOccurrence.status.in_(("skipped", "failed")),
        )
        .order_by(AgentScheduleOccurrence.created_at.desc())
        .limit(MAX_NOTIFICATIONS)
    )
    for row in bad_occurrences:
        skipped = row.status == "skipped"
        items.append(
            {
                "fact_key": f"{'schedule_skipped' if skipped else 'schedule_failed'}:{row.id}",
                "kind": "schedule_skipped" if skipped else "schedule_failed",
                "title": "一次计划未按预期运行",
                "detail": row.reason or row.status,
                "ref_id": row.schedule_id,
                "created_at": _iso(row.created_at),
            }
        )

    for item in items:
        item["read"] = item["fact_key"] in read_keys
    items.sort(key=lambda x: (x["created_at"] or ""), reverse=True)
    return items[:MAX_NOTIFICATIONS]


async def mark_read(
    session: AsyncSession, *, user_id: str, fact_keys: list[str]
) -> int:
    """Idempotently record read receipts. Returns the number of new receipts."""

    clean = list(dict.fromkeys(str(key) for key in fact_keys if key))
    if not clean or len(clean) > MAX_NOTIFICATIONS:
        raise ValueError("fact_keys must contain 1-50 keys")
    existing = set(
        await session.scalars(
            select(AgentNotificationRead.fact_key).where(
                AgentNotificationRead.user_id == user_id,
                AgentNotificationRead.fact_key.in_(clean),
            )
        )
    )
    added = 0
    for key in clean:
        if key in existing:
            continue
        session.add(AgentNotificationRead(user_id=user_id, fact_key=key))
        added += 1
    await session.flush()
    return added


async def search(
    session: AsyncSession, *, user_id: str, query: str
) -> dict[str, list[dict]]:
    """Read-only, user-scoped search across sessions, tasks, roles and schedules."""

    term = str(query).strip()
    if not term or len(term) > 200:
        raise ValueError("query must contain 1-200 characters")
    pattern = f"%{term}%"

    sessions = await session.scalars(
        select(AgentSession)
        .where(
            AgentSession.user_id == user_id,
            AgentSession.title.ilike(pattern),
        )
        .order_by(AgentSession.updated_at.desc())
        .limit(MAX_SEARCH)
    )
    tasks = await session.scalars(
        select(AgentTask)
        .where(
            AgentTask.user_id == user_id,
            (AgentTask.title.ilike(pattern) | AgentTask.input.ilike(pattern)),
        )
        .order_by(AgentTask.updated_at.desc())
        .limit(MAX_SEARCH)
    )
    roles = await session.scalars(
        select(AgentRole)
        .where(
            AgentRole.user_id == user_id,
            (AgentRole.name.ilike(pattern) | AgentRole.prompt.ilike(pattern)),
        )
        .order_by(AgentRole.updated_at.desc())
        .limit(MAX_SEARCH)
    )
    schedules = await session.scalars(
        select(AgentSchedule)
        .where(
            AgentSchedule.user_id == user_id,
            AgentSchedule.name.ilike(pattern),
        )
        .order_by(AgentSchedule.updated_at.desc())
        .limit(MAX_SEARCH)
    )
    return {
        "sessions": [
            {"id": row.id, "title": row.title, "status": row.status} for row in sessions
        ],
        "tasks": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "team_id": row.team_id,
            }
            for row in tasks
        ],
        "roles": [
            {"id": row.id, "name": row.name, "version": row.version, "state": row.state}
            for row in roles
        ],
        "schedules": [
            {
                "id": row.id,
                "name": row.name,
                "state": row.state,
                "next_due": row.next_due,
            }
            for row in schedules
        ],
    }
