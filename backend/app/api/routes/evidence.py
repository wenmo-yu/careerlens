from typing import Annotated

from anyio import to_thread
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.ingestion.files import extract_text
from app.ingestion.media import get_media_extractor
from app.models.evidence import Evidence
from app.retrieval.service import index_evidence, search_evidence
from app.schemas.evidence import EvidenceBatchRead, EvidenceRead, EvidenceTextCreate
from app.security import authorize_user
from app.services.evidence import create_evidence_chunks, get_evidence, list_evidence
from app.services.privacy import delete_evidence_record

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


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
    content = await upload.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    filename = upload.filename or "upload"
    try:
        text, file_metadata = extract_text(filename, content)
        records = await create_evidence_chunks(
            session,
            user_id=user_id,
            source_type=source_type,
            source_name=filename,
            content=text,
            metadata={"content_type": upload.content_type, **file_metadata},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EvidenceBatchRead(items=records, count=len(records))


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
    content = await upload.read(settings.media_upload_max_bytes + 1)
    if len(content) > settings.media_upload_max_bytes:
        raise HTTPException(status_code=413, detail="Media file is too large")
    filename = upload.filename or "media-upload"
    try:
        extractor = get_media_extractor()
        text, media_metadata = await to_thread.run_sync(extractor.extract, filename, content)
        records = await create_evidence_chunks(
            session,
            user_id=user_id,
            source_type=source_type,
            source_name=filename,
            content=text,
            metadata={"content_type": upload.content_type, **media_metadata},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return EvidenceBatchRead(items=records, count=len(records))


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
    result = await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
    items, diagnostics = await search_evidence(
        user_id=user_id,
        query=query,
        evidence=list(result),
        limit=limit,
    )
    return {"items": items, "count": len(items), "retrieval": diagnostics}


@router.post("/reindex/{user_id}")
async def reindex_user_evidence(
    user_id: str, session: Session, authorization: Authorization = None
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    result = await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
    records = list(result)
    if not records:
        raise HTTPException(status_code=404, detail="No evidence found for this user")
    try:
        return await index_evidence(records, strict=True)
    except Exception as exc:
        detail = f"Qdrant indexing failed: {type(exc).__name__}"
        raise HTTPException(status_code=503, detail=detail) from exc


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
    evidence_id: str, session: Session, authorization: Authorization = None
) -> dict:
    record = await get_evidence(session, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    principal = await authorize_user(
        session,
        user_id=record.user_id,
        authorization=authorization,
        required_scope="delete",
    )
    return await delete_evidence_record(session, record=record, principal=principal)

