"""Heartbeat writes and reads for long-running local processes.

A heartbeat is a liveness signal, not a business fact. Workers and the
scheduler write it to the same database as runs; API health and runtime status
read it with an explicit staleness threshold.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.heartbeat import HEARTBEAT_ROLES, RuntimeHeartbeat
from app.runtime.store import dialect_insert, now_seconds


async def beat(session: AsyncSession, role: str, instance_id: str) -> None:
    if role not in HEARTBEAT_ROLES:
        raise ValueError(f"Unknown heartbeat role: {role}")
    now = now_seconds()
    await session.execute(
        dialect_insert(session, RuntimeHeartbeat)
        .values(
            role=role,
            instance_id=instance_id,
            pid=os.getpid(),
            heartbeat_at=now,
            started_at=now,
        )
        .on_conflict_do_update(
            index_elements=["role"],
            set_={"instance_id": instance_id, "pid": os.getpid(), "heartbeat_at": now},
        )
    )
    await session.flush()


async def read_status(
    session: AsyncSession, *, stale_after_seconds: int, now: int | None = None
) -> dict[str, dict[str, Any]]:
    moment = now if now is not None else now_seconds()
    result: dict[str, dict[str, Any]] = {}
    for role in HEARTBEAT_ROLES:
        record = await session.get(RuntimeHeartbeat, role)
        if record is None:
            result[role] = {"healthy": False, "state": "not_started", "age_seconds": None}
            continue
        age = max(0, moment - record.heartbeat_at)
        result[role] = {
            "healthy": age <= stale_after_seconds,
            "state": "ok" if age <= stale_after_seconds else "stale",
            "age_seconds": age,
            "instance_id": record.instance_id,
            "pid": record.pid,
            "started_at": record.started_at,
        }
    return result
