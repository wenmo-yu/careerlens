"""M8 in-app notification centre and user-scoped task search."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.runtime.agent import inbox as inbox_service
from app.schemas.agent_inbox import MarkReadRequest, MarkReadResult, NotificationRead
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.get("/agent/notifications", response_model=list[NotificationRead])
async def list_notifications(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await inbox_service.list_notifications(session, user_id=user_id)


@router.post("/agent/notifications/read", response_model=MarkReadResult)
async def mark_notifications_read(
    payload: MarkReadRequest, session: Session, authorization: Authorization = None
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        added = await inbox_service.mark_read(
            session, user_id=payload.user_id, fact_keys=payload.fact_keys
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await session.commit()
    return {"added": added}


@router.get("/agent/search")
async def search_agent_items(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await inbox_service.search(session, user_id=user_id, query=q)
