import asyncio
from pathlib import Path
from typing import Annotated

from anyio import to_thread
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pymupdf import FileDataError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.ingestion.contract import source_fingerprint
from app.ingestion.media import OptionalMultimodalExtractor, get_media_extractor, parse_media
from app.models.evidence import Evidence
from app.models.parsed_block import ParsedBlock
from app.models.source_document import SourceDocument
from app.retrieval.service import search_evidence
from app.runtime.index_outbox import enqueue_index, try_index_now
from app.runtime.operations import ParserUnavailable, parse_in_process
from app.runtime.parse_input import parse_upload
from app.runtime.store import DELETION, StaleInput, read_scope, scope
from app.schemas.evidence import EvidenceBatchRead, EvidenceRead, EvidenceTextCreate
from app.security import authorize_user
from app.services.evidence import create_evidence_chunks, get_evidence, list_evidence
from app.services.privacy import delete_evidence_record
from app.services.source_ingestion import ingest_source_document

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _document_import_result(
    session: AsyncSession, user_id: str, source_hash: str, records: list,
) -> EvidenceBatchRead:
    """HY4-A: build an explainable result for file/media imports.

    The source document is the parse authority (parse_status, page count); the
    parsed blocks tell us how much text was actually readable and how many
    pages are still waiting for OCR. A successful task is not the same as a
    successful read — scanned-only PDFs keep ocr_pending blocks and produce no
    Evidence, which must be visible to the user instead of looking like a
    silent success.
    """
    document = (
        await session.scalars(
            select(SourceDocument).where(
                SourceDocument.user_id == user_id,
                SourceDocument.source_hash == source_hash,
            )
        )
    ).first()
    warnings: list[str] = []
    if document is None:
        return EvidenceBatchRead(
            items=records, count=len(records),
            readable_count=len(records), warnings=warnings,
        )
    blocks = list(
        await session.scalars(
            select(ParsedBlock).where(ParsedBlock.doc_id == document.id)
        )
    )
    pending = sum(1 for block in blocks if block.source_metadata.get("ocr_pending"))
    readable = sum(
        1 for block in blocks
        if block.content.strip() and not block.source_metadata.get("ocr_pending")
    )
    if pending:
        warnings.append(
            f"有 {pending} 页待 OCR；任务成功不等于已读出文字，这些页面暂未形成证据。"
        )
    if not readable and pending:
        warnings.append(
            "本次只识别到扫描页，尚未生成可读证据；请补充 OCR 能力或换用带文字层的 PDF。"
        )
    parse_status = document.parse_status
    if parse_status == "parsed" and pending:
        parse_status = "partial"
    return EvidenceBatchRead(
        items=records,
        count=len(records),
        parse_status=parse_status,
        source_document_id=document.id,
        readable_count=readable,
        ocr_pending_count=pending,
        warnings=warnings,
    )


@router.post("/text", response_model=EvidenceBatchRead, status_code=status.HTTP_201_CREATED)
async def ingest_text(
    payload: EvidenceTextCreate,
    session: Session,
    authorization: Authorization = None,
) -> EvidenceBatchRead:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="write",
    )
    try:
        records = await create_evidence_chunks(
            session,
            user_id=payload.user_id,
            source_type=payload.source_type,
            source_name=payload.source_name,
            content=payload.content,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EvidenceBatchRead(items=records, count=len(records))


@router.post("/file", response_model=EvidenceBatchRead, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    source_type: Annotated[str, Form(max_length=50)] = "resume",
    authorization: Authorization = None,
) -> EvidenceBatchRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    settings = get_settings()
    epoch = await read_scope(session, user_id, DELETION)
    try:
        content = await upload.read(settings.upload_max_bytes + 1)
    finally:
        await upload.close()
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    filename = upload.filename or "upload"
    source_hash = source_fingerprint(content)
    try:
        if Path(filename).suffix.lower() in {".docx", ".xlsx", ".pdf", ".zip"}:
            async with asyncio.timeout(30):
                parsed = await parse_in_process("file_import", filename, content)
        else:
            parsed = await to_thread.run_sync(parse_upload, "file_import", filename, content)
        records = await ingest_source_document(
            session,
            user_id=user_id,
            source_type=source_type,
            filename=filename,
            mime_type=upload.content_type,
            file_size=len(content),
            source_hash=source_hash,
            parsed=parsed,
            expected_deletion=epoch,
        )
    except StaleInput as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Document parsing exceeded its time limit") from exc
    except (ValueError, FileDataError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _document_import_result(session, user_id, source_hash, records)


@router.post("/media", response_model=EvidenceBatchRead, status_code=status.HTTP_201_CREATED)
async def ingest_media(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    source_type: Annotated[str, Form(max_length=50)] = "personal_media",
    authorization: Authorization = None,
) -> EvidenceBatchRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    settings = get_settings()
    epoch = await read_scope(session, user_id, DELETION)
    try:
        content = await upload.read(settings.media_upload_max_bytes + 1)
    finally:
        await upload.close()
    if len(content) > settings.media_upload_max_bytes:
        raise HTTPException(status_code=413, detail="Media file is too large")
    filename = upload.filename or "media-upload"
    source_hash = source_fingerprint(content)
    try:
        extractor = get_media_extractor()
        async with asyncio.timeout(settings.run_timeout_seconds):
            if isinstance(extractor, OptionalMultimodalExtractor):
                parsed = await parse_in_process("media_import", filename, content)
            else:
                parsed = await to_thread.run_sync(parse_media, extractor, filename, content)
        records = await ingest_source_document(
            session,
            user_id=user_id,
            source_type=source_type,
            filename=filename,
            mime_type=upload.content_type,
            file_size=len(content),
            source_hash=source_hash,
            parsed=parsed,
            expected_deletion=epoch,
        )
    except StaleInput as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ParserUnavailable as exc:
        raise HTTPException(status_code=503, detail="Media parser is unavailable") from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Media parsing exceeded its time limit") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await _document_import_result(session, user_id, source_hash, records)


@router.get("", response_model=EvidenceBatchRead)
async def read_evidence_list(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    source_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: Authorization = None,
) -> EvidenceBatchRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    records = await list_evidence(
        session,
        user_id=user_id,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return EvidenceBatchRead(items=records, count=len(records))


@router.get("/search")
async def search_user_evidence(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    query: Annotated[str, Query(min_length=1, max_length=2000)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    items, diagnostics = await search_evidence(
        user_id=user_id,
        query=query,
        session=session,
        limit=limit,
    )
    return {"items": items, "count": len(items), "retrieval": diagnostics}


@router.post("/reindex/{user_id}")
async def reindex_user_evidence(
    user_id: str, session: Session, authorization: Authorization = None
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write", touch=False
    )
    await scope(session, user_id)
    result = await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
    records = list(result)
    if not records:
        raise HTTPException(status_code=404, detail="No evidence found for this user")
    ids = [item.id for item in records]
    for offset in range(0, len(ids), 500):
        await enqueue_index(session, user_id, ids[offset:offset + 500])
    await session.commit()
    await try_index_now(session, ids)
    backend = get_settings().retrieval_backend
    return {
        "status": "skipped" if backend == "local" else "queued",
        "backend": "local" if backend == "local" else "qdrant",
        "scheduled": 0 if backend == "local" else len(ids),
    }


@router.get("/{evidence_id}", response_model=EvidenceRead)
async def read_evidence(
    evidence_id: str, session: Session, authorization: Authorization = None
) -> EvidenceRead:
    record = await get_evidence(session, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await authorize_user(
        session,
        user_id=record.user_id,
        authorization=authorization,
        required_scope="read",
    )
    return EvidenceRead.model_validate(record)


@router.delete("/{evidence_id}")
async def delete_evidence(
    evidence_id: str, session: Session, authorization: Authorization = None,
) -> dict:
    record = await get_evidence(session, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    principal = await authorize_user(
        session,
        user_id=record.user_id,
        authorization=authorization,
        required_scope="delete",
        touch=False,
    )
    return await delete_evidence_record(session, record=record, principal=principal)

