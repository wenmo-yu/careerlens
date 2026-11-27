"""Build and verify a new Qdrant collection during a maintenance window."""

import argparse
import asyncio

from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models.evidence import Evidence
from app.retrieval.generations import register_collection
from app.retrieval.qdrant_store import MANIFEST_ID, IndexIncompatible, QdrantEvidenceStore
from app.retrieval.service import get_qdrant_store


async def rebuild(factory: async_sessionmaker, store: QdrantEvidenceStore) -> int:
    # Register first so deletion can find even a failed/unfinished build.
    async with factory.begin() as session:
        if not await register_collection(session):
            raise IndexIncompatible("Choose a new collection name for the changed model")
    await asyncio.to_thread(store.ensure_collection, building=True)
    total = 0
    cursor = ""
    while True:
        async with factory() as session:
            rows = list(await session.scalars(select(Evidence).where(Evidence.id > cursor)
                .order_by(Evidence.id).limit(64)))
        if not rows:
            break
        await asyncio.to_thread(store.index, rows, building=True)
        indexed = await asyncio.to_thread(
            store.client.retrieve, store.collection_name, [item.id for item in rows],
            with_payload=["user_id"],
        )
        expected = {item.id: item.user_id for item in rows}
        actual = {str(row.id): (row.payload or {}).get("user_id") for row in indexed}
        if expected != actual:
            raise IndexIncompatible("Indexed IDs or tenant ownership do not match the database")
        total += len(rows)
        cursor = rows[-1].id
    indexed_count = await asyncio.to_thread(
        store.client.count, store.collection_name,
        count_filter=models.Filter(must_not=[models.HasIdCondition(has_id=[MANIFEST_ID])]),
        exact=True,
    )
    if indexed_count.count != total:
        raise IndexIncompatible("Collection contains unexpected points; choose a clean target")
    await asyncio.to_thread(store.write_manifest, "ready")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writes-paused", action="store_true", help="Confirm writers are stopped")
    args = parser.parse_args()
    if not args.writes_paused:
        parser.error("Stop API/MCP/Workers or place the instance in read-only maintenance first")
    if get_settings().retrieval_backend == "local":
        parser.error("Set RETRIEVAL_BACKEND=auto or qdrant for the rebuild")
    count = asyncio.run(rebuild(SessionFactory, get_qdrant_store()))
    print(f"Verified {count} evidence points")


if __name__ == "__main__":
    main()
