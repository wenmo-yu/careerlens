from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.evidence import Evidence
from app.schemas.wiki import (
    WikiCompileRead,
    WikiCompileRequest,
    WikiPageRead,
    WikiRevertRequest,
)
from app.security import authorize_user
from app.services.wiki_pages import (
    WikiRevisionNotFound,
    get_page,
    list_pages,
    list_revisions,
    revert_page,
)
from app.wiki.compiler import WikiCompileError, compile_page

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/compile", response_model=WikiCompileRead, status_code=201)
async def compile_wiki_page(
    payload: WikiCompileRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> WikiCompileRead:
    """Build-time product: compile selected evidence into a Wiki page.

    Selecting wiki at build time calls this endpoint; the resulting WikiPage is
    a solidified product. ``base_version`` guards recompiles against stale runs.
    """
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="write",
    )
    sources: list[dict] = []
    if payload.evidence_ids:
        records = list(
            await session.scalars(
                select(Evidence).where(
                    Evidence.user_id == payload.user_id,
                    Evidence.id.in_(payload.evidence_ids),
                )
            )
        )
        sources = [
            {"evidence_id": item.id, "content": item.content} for item in records
        ]
    try:
        page, diagnostics = await compile_page(
            session,
            user_id=payload.user_id,
            slug=payload.slug,
            title=payload.title,
            sources=sources,
            base_version=payload.base_version,
            edit_source=payload.edit_source,
            source_refs=payload.evidence_ids,
        )
    except WikiCompileError as exc:
        # A stale base_version is wrapped by the compiler; detect via message.
        if "version changed" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WikiCompileRead(page=WikiPageRead.model_validate(page), diagnostics=diagnostics)


@router.get("", response_model=list[WikiPageRead])
async def get_wiki_pages(
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[WikiPageRead]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    pages = await list_pages(session, user_id=user_id)
    return [WikiPageRead.model_validate(page) for page in pages]


@router.get("/{slug}", response_model=WikiPageRead)
async def get_wiki_page(
    slug: str,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> WikiPageRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    page = await get_page(session, user_id=user_id, slug=slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    return WikiPageRead.model_validate(page)


@router.post("/{slug}/revert", response_model=WikiPageRead)
async def revert_wiki_page(
    slug: str,
    payload: WikiRevertRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> WikiPageRead:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="write",
    )
    page = await get_page(session, user_id=payload.user_id, slug=slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    try:
        reverted = await revert_page(
            session, page=page, target_version=payload.target_version
        )
    except WikiRevisionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiPageRead.model_validate(reverted)


@router.get("/{slug}/revisions", response_model=list[dict])
async def get_wiki_revisions(
    slug: str,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    page = await get_page(session, user_id=user_id, slug=slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    revisions = await list_revisions(session, user_id=user_id, page_id=page.id)
    return [
        {
            "version": r.version,
            "edit_source": r.edit_source,
            "title": r.title,
            "summary": r.summary,
            "edited_at": r.edited_at.isoformat(),
        }
        for r in revisions
    ]
