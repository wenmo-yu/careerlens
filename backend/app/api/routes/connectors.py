from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import parse_bilibili_export, parse_browser_capture, parse_weibo_export
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.evidence import ConnectorImportRead
from app.security import authorize_user
from app.services.connectors import import_connector_items

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/browser/import",
    response_model=ConnectorImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_browser_capture(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorImportRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    content = await upload.read(2_000_001)
    try:
        items, skipped, platform = parse_browser_capture(content)
        records, duplicates = await import_connector_items(
            session,
            user_id=user_id,
            source_type=f"{platform}_browser",
            items=items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConnectorImportRead(
        items=records,
        created_count=len(records),
        skipped_count=skipped,
        duplicate_count=duplicates,
        connector=f"{platform}_browser_capture",
    )


@router.post(
    "/bilibili/import",
    response_model=ConnectorImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_bilibili_export(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorImportRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    settings = get_settings()
    content = await upload.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Export file is too large")
    try:
        items, skipped = parse_bilibili_export(content)
        records, duplicates = await import_connector_items(
            session,
            user_id=user_id,
            source_type="bilibili",
            items=items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConnectorImportRead(
        items=records,
        created_count=len(records),
        skipped_count=skipped,
        duplicate_count=duplicates,
        connector="bilibili_export",
    )


@router.post(
    "/weibo/import",
    response_model=ConnectorImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_weibo_export(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorImportRead:
    """Import a user-provided UTF-8 Weibo JSON or CSV export without platform login."""
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    settings = get_settings()
    content = await upload.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Export file is too large")
    try:
        items, skipped = parse_weibo_export(content, upload.filename)
        records, duplicates = await import_connector_items(
            session,
            user_id=user_id,
            source_type="weibo",
            items=items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConnectorImportRead(
        items=records,
        created_count=len(records),
        skipped_count=skipped,
        duplicate_count=duplicates,
        connector="weibo_export",
    )
