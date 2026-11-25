from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import parse_bilibili_export, parse_browser_capture, parse_weibo_export
from app.connectors.github import GitHubImportError, fetch_github_items
from app.connectors.public_link import PublicLinkCard, build_public_link_items
from app.connectors.registry import list_sources
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.evidence import ConnectorImportRead
from app.security import authorize_user
from app.services.connectors import import_connector_items

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/registry")
async def get_source_registry() -> dict:
    """HY4-D: what the Import Hub supports. No credentials, no network."""
    return {"sources": list_sources()}


class PublicLinkImport(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    cards: list[PublicLinkCard] = Field(min_length=1, max_length=50)


@router.post(
    "/public-link/import",
    response_model=ConnectorImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_public_links(
    payload: PublicLinkImport,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorImportRead:
    """Store user-pasted link cards. The URL is never fetched."""
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    items, skipped = build_public_link_items(payload.cards)
    records, duplicates = await import_connector_items(
        session, user_id=payload.user_id, source_type="public_link", items=items
    )
    return ConnectorImportRead(
        items=records,
        created_count=len(records),
        skipped_count=skipped + duplicates,
        duplicate_count=duplicates,
        connector="public_link_card",
    )


class GitHubImportRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    token: str = Field(min_length=20, max_length=255)
    repos: list[str] = Field(default_factory=list, max_length=20)


@router.post(
    "/github/import",
    response_model=ConnectorImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_github(
    payload: GitHubImportRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorImportRead:
    """Read repos with the user's own read-only token. The token is not stored."""
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    try:
        items, skipped = await fetch_github_items(
            token=payload.token, repos=payload.repos
        )
        records, duplicates = await import_connector_items(
            session, user_id=payload.user_id, source_type="github", items=items
        )
    except GitHubImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="连接 GitHub 失败，请检查网络后重试；令牌未被保存。"
        ) from exc
    return ConnectorImportRead(
        items=records,
        created_count=len(records),
        skipped_count=skipped + duplicates,
        duplicate_count=duplicates,
        connector="github_token",
    )


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
