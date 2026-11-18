from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.ingestion.chunking import chunk_text
from app.ingestion.contract import content_fingerprint
from app.models.evidence import Evidence
from app.retrieval.service import index_evidence


def _source_entry(source_type: str, source_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"source_type": source_type, "source_name": source_name}
    entry.update(metadata)
    return entry


def _append_source(record: Evidence, entry: dict[str, Any]) -> bool:
    """Append a source to an existing evidence row; return True if it was new."""
    metadata = record.source_metadata or {}
    sources = list(metadata.get("sources", []))
    if any(
        item.get("source_type") == entry["source_type"]
        and item.get("source_name") == entry["source_name"]
        for item in sources
    ):
        return False
    sources.append(entry)
    metadata["sources"] = sources
    metadata["source_count"] = len(sources)
    # JSON columns are not dirty-tracked on in-place mutation; explicitly flag
    # so the appended source is persisted.
    flag_modified(record, "source_metadata")
    return True


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

    fingerprints = [content_fingerprint(chunk) for chunk in chunks]
    existing: dict[str, Evidence] = {}
    if dedup:
        hashes = set(fingerprints)
        if hashes:
            result = await session.scalars(
                select(Evidence).where(
                    Evidence.user_id == user_id,
                    Evidence.content_hash.in_(hashes),
                )
            )
            existing = {record.content_hash: record for record in result}

    entry = _source_entry(source_type, source_name, metadata or {})
    base_metadata: dict[str, Any] = dict(metadata or {})
    resolved: list[Evidence] = []
    fresh: list[Evidence] = []
    for chunk, fingerprint in zip(chunks, fingerprints, strict=True):
        record = existing.get(fingerprint)
        if record is not None:
            _append_source(record, entry)
            resolved.append(record)
            continue
        record = Evidence(
            user_id=user_id,
            source_type=source_type,
            source_name=source_name,
            content=chunk,
            chunk_index=len(resolved) + len(fresh),
            source_metadata={**base_metadata, "sources": [entry], "source_count": 1},
            content_hash=fingerprint,
        )
        session.add(record)
        fresh.append(record)
        resolved.append(record)

    if commit:
        await session.commit()
        for record in fresh:
            await session.refresh(record)
    else:
        await session.flush()
    if fresh:
        await index_evidence(fresh)
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
        query.order_by(Evidence.created_at.desc(), Evidence.chunk_index)
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(query)
    return list(result)


async def get_evidence(session: AsyncSession, evidence_id: str) -> Evidence | None:
    return await session.get(Evidence, evidence_id)
