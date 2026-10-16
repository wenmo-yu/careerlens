from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.auth import AuditEventRead
from app.schemas.privacy import AccountDeletionRead
from app.security import authorize_user
from app.services.audit import list_audit_events
from app.services.privacy import delete_user_account, export_user_data

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{user_id}/export")
async def export_data(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    principal = await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="export",
    )
    return await export_user_data(session, principal=principal)


@router.get("/{user_id}/audit", response_model=list[AuditEventRead])
async def get_audit_log(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventRead]:
    await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="read",
    )
    return await list_audit_events(session, user_id=user_id, limit=limit)


@router.delete("/{user_id}", response_model=AccountDeletionRead)
async def delete_account(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> AccountDeletionRead:
    principal = await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="delete",
    )
    return AccountDeletionRead.model_validate(
        await delete_user_account(session, principal=principal)
    )
