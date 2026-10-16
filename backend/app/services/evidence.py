from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunking import chunk_text
from app.models.evidence import Evidence
from app.retrieval.service import index_evidence


async def create_evidence_chunks(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    source_name: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> list[Evidence]:
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("No readable text was found")

    records = [
        Evidence(
            user_id=user_id,
            source_type=source_type,
            source_name=source_name,
            content=chunk,
            chunk_index=index,
            source_metadata=metadata or {},
        )
        for index, chunk in enumerate(chunks)
    ]
    session.add_all(records)
    await session.commit()
    for record in records:
        await session.refresh(record)
    await index_evidence(records)
    return records


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

