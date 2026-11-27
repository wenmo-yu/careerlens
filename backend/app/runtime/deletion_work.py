"""Lease persistent cleanup work after the relational deletion has committed."""

import asyncio
from uuid import uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.graph.checkpoint import delete_postgres_checkpoint
from app.models.account_deletion import DeletionWork
from app.retrieval.service import delete_user_index
from app.runtime.store import now_seconds


async def process_deletion_work(factory: async_sessionmaker) -> bool:
    lease = str(uuid4())
    now = now_seconds()
    async with factory.begin() as session:
        if session.get_bind().dialect.name == "sqlite":
            await session.execute(
                update(DeletionWork).where(DeletionWork.id == "").values(ready_at=0)
            )
        work = await session.scalar(
            select(DeletionWork).where(
                DeletionWork.status == "pending", DeletionWork.ready_at <= now,
                or_(DeletionWork.lease_until.is_(None), DeletionWork.lease_until <= now),
            ).order_by(DeletionWork.ready_at, DeletionWork.id).limit(1)
            .with_for_update(skip_locked=True)
        )
        if work is None:
            return False
        work.lease_token = lease
        work.lease_until = now + 60
        work.attempts += 1
        work_id, kind, subject, collection, attempts = (
            work.id, work.kind, work.subject, work.collection, work.attempts,
        )

    error = None
    try:
        async with asyncio.timeout(20):
            if not subject:
                raise RuntimeError("Cleanup target is missing")
            if kind == "checkpoint":
                await delete_postgres_checkpoint(subject)
            elif kind == "vector_user" and collection:
                outcome = await delete_user_index(subject, collection=collection)
                if outcome["status"] != "deleted":
                    raise RuntimeError("Vector storage is unavailable")
            else:
                raise RuntimeError("Unsupported cleanup target")
    except Exception as exc:
        error = type(exc).__name__

    owner = (DeletionWork.id == work_id, DeletionWork.lease_token == lease)
    async with factory.begin() as session:
        if error is None:
            await session.execute(delete(DeletionWork).where(
                *owner, DeletionWork.receipt_id.is_(None),
            ))
            values = {"status": "completed", "subject": None}
        elif attempts >= 12:
            values = {"status": "failed"}
        else:
            values = {"ready_at": now_seconds() + min(300, 2 ** min(attempts, 9))}
        await session.execute(update(DeletionWork).where(*owner).values(
            lease_token=None, lease_until=None, last_error=error, **values,
        ))
    return True
