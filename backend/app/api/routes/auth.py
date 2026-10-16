import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.models.access_token import AccessToken
from app.schemas.auth import RegisterRequest, TokenCreated, TokenCreateRequest, TokenRead
from app.security import authorize_user
from app.security.auth import create_access_token

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


def _created(record: AccessToken, raw_token: str) -> TokenCreated:
    return TokenCreated(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        scopes=record.scopes,
        token=raw_token,
        created_at=record.created_at,
    )


@router.post("/register", response_model=TokenCreated)
async def register_owner(
    payload: RegisterRequest,
    session: Session,
    registration_secret: Annotated[str | None, Header(alias="X-Registration-Secret")] = None,
) -> TokenCreated:
    settings = get_settings()
    if settings.auth_registration_secret and not secrets.compare_digest(
        registration_secret or "", settings.auth_registration_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid registration secret")
    existing = await session.scalar(
        select(AccessToken.id).where(AccessToken.user_id == payload.user_id).limit(1)
    )
    if existing:
        raise HTTPException(status_code=409, detail="This user already has an owner token")
    record, raw_token = await create_access_token(
        session,
        user_id=payload.user_id,
        name=payload.name,
        scopes=["read", "write", "export", "delete", "manage"],
    )
    return _created(record, raw_token)


@router.post("/tokens", response_model=TokenCreated)
async def create_scoped_token(
    payload: TokenCreateRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenCreated:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="manage",
    )
    try:
        record, raw_token = await create_access_token(session, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _created(record, raw_token)


@router.get("/{user_id}/tokens", response_model=list[TokenRead])
async def list_tokens(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[TokenRead]:
    await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="manage",
    )
    result = await session.scalars(
        select(AccessToken)
        .where(AccessToken.user_id == user_id)
        .order_by(AccessToken.created_at.desc())
    )
    return list(result)


@router.delete("/{user_id}/tokens/{token_id}", response_model=TokenRead)
async def revoke_token(
    user_id: str,
    token_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenRead:
    principal = await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="manage",
    )
    record = await session.get(AccessToken, token_id)
    if record is None or record.user_id != user_id:
        raise HTTPException(status_code=404, detail="Access token not found")
    if record.id == principal.token_id:
        raise HTTPException(
            status_code=409,
            detail="Create another manager token before revoking this token",
        )
    record.active = False
    await session.commit()
    await session.refresh(record)
    return record
