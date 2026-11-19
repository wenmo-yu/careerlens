from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunking import normalize_text
from app.ingestion.contract import ParsedDocument, content_fingerprint
from app.models.evidence import Evidence
from app.models.parsed_block import ParsedBlock
from app.models.source_document import SourceDocument
from app.retrieval.service import index_evidence
from app.services.evidence import insert_no_conflict, resolve_evidence


async def ingest_source_document(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    filename: str,
    mime_type: str | None,
    file_size: int,
    source_hash: str,
    parsed: ParsedDocument,
) -> list[Evidence]:
    if not any(normalize_text(block.content) for block in parsed.blocks):
        if not any(block.source_metadata.get("ocr_pending") for block in parsed.blocks):
            raise ValueError("No readable text was found")

    metadata = {**parsed.metadata, "block_count": len(parsed.blocks)}
    await session.execute(
        insert_no_conflict(
            session,
            SourceDocument,
            {
                "user_id": user_id,
                "source_hash": source_hash,
                "filename": filename,
                "source_type": source_type,
                "mime_type": mime_type,
                "file_size": file_size,
                "page_count": metadata.get("page_count"),
                "parse_status": parsed.parse_status,
                "meta": metadata,
            },
            ["user_id", "source_hash"],
        )
    )
    document = (
        await session.scalars(
            select(SourceDocument)
            .where(SourceDocument.user_id == user_id, SourceDocument.source_hash == source_hash)
            .with_for_update()
        )
    ).one()
    existing = {
        block.block_index: block
        for block in await session.scalars(
            select(ParsedBlock).where(ParsedBlock.doc_id == document.id)
        )
    }
    records: dict[int, Evidence] = {}
    for block in sorted(parsed.blocks, key=lambda item: content_fingerprint(item.content)):
        content = block.content.strip()
        previous = existing.get(block.block_index)
        if previous is not None and previous.content_hash != content_fingerprint(content):
            if previous.evidence_id is not None:
                record = await session.get(Evidence, previous.evidence_id)
                if record is not None:
                    records[block.block_index] = record
            continue
        readable = bool(normalize_text(content))
        if not readable and not block.source_metadata.get("ocr_pending"):
            continue
        locator = {
            "doc_id": document.id,
            "block_index": block.block_index,
            "block_type": block.block_type,
            "page_no": block.page_no,
            "bbox": block.bbox,
            "time_start": block.time_start,
            "time_end": block.time_end,
            "section_path": block.section_path,
        }
        record = (
            await resolve_evidence(
                session,
                user_id=user_id,
                source_type=source_type,
                source_name=filename,
                content=content,
                chunk_index=block.block_index,
                metadata={
                    **metadata, **block.source_metadata, **locator, "content_type": mime_type,
                },
            )
            if readable
            else None
        )
        if record is not None:
            records[block.block_index] = record
        if previous is None:
            session.add(
                ParsedBlock(
                    **locator,
                    user_id=user_id,
                    evidence_id=record.id if record is not None else None,
                    content=content,
                    content_hash=content_fingerprint(content),
                    char_start=block.char_start,
                    char_end=block.char_end or len(content),
                    image_ref=block.image_ref,
                    source_type=block.source_type,
                    content_revision=block.content_revision,
                    source_metadata=block.source_metadata,
                )
            )
        elif record is not None and previous.evidence_id != record.id:
            previous.evidence_id = record.id

    await session.commit()
    resolved = list({records[index].id: records[index] for index in sorted(records)}.values())
    if resolved:
        await index_evidence(resolved)
    return resolved
