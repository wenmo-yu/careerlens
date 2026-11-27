import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.models.access_token import AccessToken
from app.runtime.store import scope
from app.schemas.auth import (
    RegisterRequest,
    SessionRead,
    TokenCreated,
    TokenCreateRequest,
    TokenRead,
)
from app.security import authorize_user
from app.security.auth import (
    ALLOWED_SCOPES,
    account_was_deleted,
    authorize_ops,
    bearer_value,
    create_access_token,
    is_ops_token,
    verify_access_token,
)

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
        audience=record.audience,
        expires_at=record.expires_at,
    )


@router.post("/register", response_model=TokenCreated)
async def register_owner(
    payload: RegisterRequest,
    session: Session,
    registration_secret: Annotated[str | None, Header(alias="X-Registration-Secret")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenCreated:
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail="Account registration is closed")
    if settings.app_env == "production":
        await authorize_ops(session, authorization=authorization)
    if settings.auth_mode != "disabled" and not settings.auth_registration_secret:
        raise HTTPException(status_code=403, detail="Registration is not configured")
    if settings.auth_registration_secret and not secrets.compare_digest(
        (registration_secret or "").encode(), settings.auth_registration_secret.encode()
    ):
        raise HTTPException(status_code=403, detail="Invalid registration secret")
    await scope(session, payload.user_id)
    if await account_was_deleted(session, payload.user_id):
        raise HTTPException(status_code=410, detail="This account identifier was retired")
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
    principal = await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="manage",
        touch=False,
    )
    allowed = ALLOWED_SCOPES if {"manage", "*"}.intersection(principal.scopes) else principal.scopes
    if not set(payload.scopes).issubset(ALLOWED_SCOPES):
        raise HTTPException(status_code=422, detail="Unsupported token scope")
    if not set(payload.scopes).issubset(allowed):
        raise HTTPException(status_code=403, detail="Cannot delegate broader scopes")
    await scope(session, payload.user_id)
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization,
        required_scope="manage", touch=False,
    )
    try:
        record, raw_token = await create_access_token(session, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _created(record, raw_token)


@router.get("/me", response_model=SessionRead)
async def current_session(
    session: Session, authorization: Annotated[str | None, Header()] = None,
) -> SessionRead:
    settings = get_settings()
    result = SessionRead(
        mode=settings.auth_mode,
        can_operate=settings.auth_mode == "disabled" and settings.app_env != "production",
        registration_enabled=settings.registration_enabled and settings.app_env != "production",
    )
    if not authorization or settings.auth_mode == "disabled":
        return result
    raw_token = bearer_value(authorization)
    if is_ops_token(raw_token):
        return result.model_copy(update={"can_operate": True})
    record = await verify_access_token(session, raw_token)
    if record is None or await account_was_deleted(session, record.user_id):
        raise HTTPException(status_code=401, detail="Invalid, expired or revoked access token")
    return result.model_copy(update={"user_id": record.user_id, "scopes": record.scopes})


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
    await authorize_user(
        session,
        user_id=user_id,
        authorization=authorization,
        required_scope="manage",
        touch=False,
    )
    await scope(session, user_id)
    principal = await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="manage",
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
