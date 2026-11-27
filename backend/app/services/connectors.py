from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorItem
from app.models.evidence import Evidence
from app.runtime.index_outbox import try_index_now
from app.runtime.store import check_write_scope
from app.services.evidence import create_evidence_chunks


async def import_connector_items(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    items: list[ConnectorItem],
    expected_deletion: int | None = None,
) -> tuple[list[Evidence], int]:
    await check_write_scope(session, user_id, expected_deletion=expected_deletion, bump=True)
    current = await session.scalars(
        select(Evidence).where(
            Evidence.user_id == user_id,
            Evidence.source_type == source_type,
        )
    )
    known_ids = {
        str(item.source_metadata.get("connector_item_id"))
        for item in current
        if item.source_metadata.get("connector_item_id") is not None
    }
    created: list[Evidence] = []
    duplicate_count = 0
    for item in items:
        if item.external_id in known_ids:
            duplicate_count += 1
            continue
        records = await create_evidence_chunks(
            session,
            user_id=user_id,
            source_type=source_type,
            source_name=item.source_name,
            content=item.content,
            metadata=item.metadata,
            commit=False,
        )
        created.extend(records)
        known_ids.add(item.external_id)
    await session.commit()
    await try_index_now(session, [record.id for record in created])
    return created, duplicate_count
