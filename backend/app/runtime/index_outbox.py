from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.evidence import Evidence
from app.models.run import EvidenceIndexWork
from app.retrieval.generations import cleanup_collections, register_collection
from app.retrieval.service import delete_evidence_index, index_evidence
from app.runtime.store import dialect_insert, now_seconds


async def enqueue_index(
    session: AsyncSession, user_id: str, ids: list[str], *, action: str = "upsert"
) -> None:
    if not ids or (action == "upsert" and get_settings().retrieval_backend == "local"):
        return
    if action == "upsert":
        await register_collection(session)
    rows = [
        {"evidence_id": evidence_id, "user_id": user_id, "action": action}
        for evidence_id in sorted(set(ids))
    ]
    statement = dialect_insert(session, EvidenceIndexWork).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["evidence_id"],
            set_={"action": action, "ready_at": 0, "attempts": 0},
        )
    )


async def process_index_work(session: AsyncSession, evidence_id: str | None = None) -> bool:
    query = (
        select(EvidenceIndexWork)
        .where(EvidenceIndexWork.ready_at <= now_seconds())
        .order_by(EvidenceIndexWork.ready_at, EvidenceIndexWork.evidence_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if evidence_id is not None:
        query = query.where(EvidenceIndexWork.evidence_id == evidence_id)
    if get_settings().retrieval_backend == "local":
        query = query.where(EvidenceIndexWork.action == "delete")
    if session.get_bind().dialect.name == "sqlite":
        await session.execute(
            update(EvidenceIndexWork).where(EvidenceIndexWork.evidence_id == "")
            .values(ready_at=0)
        )
    work = await session.scalar(query)
    if work is None:
        return False
    record = await session.scalar(
        select(Evidence).where(Evidence.id == work.evidence_id, Evidence.user_id == work.user_id)
    )
    try:
        if work.action == "delete" or record is None:
            outcome = await delete_evidence_index(
                work.evidence_id, strict=True, collections=await cleanup_collections(session),
            )
        else:
            outcome = await index_evidence([record], strict=True)
        if outcome["status"] not in {"deleted", "ok"}:
            raise RuntimeError("index unavailable")
    except Exception:
        work.attempts += 1
        work.ready_at = now_seconds() + min(300, 2 ** min(work.attempts, 9))
    else:
        await session.delete(work)
    return True


async def try_index_now(session: AsyncSession, ids: list[str]) -> None:
    if get_settings().retrieval_backend == "local":
        return
    for evidence_id in sorted(set(ids))[:4]:
        try:
            await process_index_work(session, evidence_id)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            return
