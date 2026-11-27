from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunking import chunk_text
from app.ingestion.claim_strength import classify_claim_strength
from app.ingestion.contract import content_fingerprint
from app.models.evidence import Evidence
from app.runtime.index_outbox import enqueue_index, try_index_now
from app.runtime.store import check_write_scope


def _source_entry(source_type: str, source_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {**metadata, "source_type": source_type, "source_name": source_name}


def _append_source(record: Evidence, entry: dict[str, Any]) -> bool:
    """Append a source to an existing evidence row; return True if it was new."""
    metadata = record.source_metadata or {}
    sources = list(metadata.get("sources", []))
    if entry in sources:
        return False
    sources.append(entry)
    record.source_metadata = {**metadata, "sources": sources, "source_count": len(sources)}
    return True


def insert_no_conflict(session: AsyncSession, model, values: dict, keys: list[str]):
    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgres_insert
    return insert(model).values(**values).on_conflict_do_nothing(index_elements=keys)


async def resolve_evidence(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    source_name: str,
    content: str,
    chunk_index: int,
    metadata: dict[str, Any],
    dedup: bool = True,
) -> Evidence:
    fingerprint = content_fingerprint(content) if dedup else None
    query = (
        select(Evidence)
        .where(Evidence.user_id == user_id, Evidence.content_hash == fingerprint)
        .with_for_update()
    )
    entry = _source_entry(source_type, source_name, metadata)
    values = {
        "user_id": user_id,
        "source_type": source_type,
        "source_name": source_name,
        "content": content,
        "chunk_index": chunk_index,
        "source_metadata": {**metadata, "sources": [entry], "source_count": 1},
        "content_hash": fingerprint,
    }
    if not dedup:
        record = Evidence(**values)
        session.add(record)
        await session.flush()
        return record
    record = await session.scalar(query)
    if record is None:
        statement = insert_no_conflict(
            session, Evidence, values, ["user_id", "content_hash"]
        )
        await session.execute(statement)
        record = (await session.scalars(query)).one()
    _append_source(record, entry)
    return record


async def create_evidence_chunks(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    source_name: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
    dedup: bool = True,
) -> list[Evidence]:
    """Create evidence chunks with source-level deduplication.

    Text is split into chunks; each chunk's sha256 (``user_id + content_hash``)
    identifies an evidence row. When identical text arrives again — from the
    same file re-uploaded or a different source — the existing row is reused
    and the new origin is appended to ``source_metadata["sources"]``. This keeps
    one evidence per unique text while retaining every source reference, so a
    re-upload cannot inflate the profile's source count.

    Set ``commit=False`` when composing a larger atomic unit; rows are flushed
    so IDs exist, but the caller owns the transaction. Set ``dedup=False`` only
    for flows that deliberately want duplicate rows (rare).
    """
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("No readable text was found")
    if commit:
        await check_write_scope(session, user_id, bump=True)

    effective_metadata = classify_claim_strength(content, metadata or {})
    records: dict[int, Evidence] = {}
    ordered_chunks = sorted(enumerate(chunks), key=lambda item: content_fingerprint(item[1]))
    for index, chunk in ordered_chunks:
        records[index] = await resolve_evidence(
            session, user_id=user_id, source_type=source_type, source_name=source_name,
            content=chunk, chunk_index=index, metadata=effective_metadata, dedup=dedup,
        )
    resolved = list({records[index].id: records[index] for index in range(len(chunks))}.values())
    evidence_ids = [record.id for record in resolved]
    await enqueue_index(session, user_id, evidence_ids)
    if commit:
        await session.commit()
        await try_index_now(session, evidence_ids)
    else:
        await session.flush()
    return resolved


async def list_evidence(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Evidence]:
    query = select(Evidence).where(Evidence.user_id == user_id)
    if source_type:
        query = query.where(Evidence.source_type == source_type)
    query = (
        query.order_by(Evidence.created_at.desc(), Evidence.chunk_index, Evidence.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(query)
    return list(result)


async def get_evidence(session: AsyncSession, evidence_id: str) -> Evidence | None:
    return await session.get(Evidence, evidence_id)
