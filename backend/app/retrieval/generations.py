from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.index_generation import IndexGeneration
from app.retrieval.providers import embedding_fingerprint
from app.runtime.store import dialect_insert


async def register_collection(session: AsyncSession) -> bool:
    settings = get_settings()
    name = settings.qdrant_collection
    fingerprint = embedding_fingerprint(settings)
    await session.execute(dialect_insert(session, IndexGeneration).values(
        collection=name, fingerprint=fingerprint,
    ).on_conflict_do_nothing(index_elements=["collection"]))
    recorded = await session.get(IndexGeneration, name)
    return recorded is not None and recorded.fingerprint == fingerprint


async def cleanup_collections(session: AsyncSession) -> tuple[str, ...]:
    registered = await session.scalars(select(IndexGeneration.collection))
    return tuple(sorted(set(registered).union(get_settings().cleanup_collections)))
