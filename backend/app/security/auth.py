import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.access_token import AccessToken

ALLOWED_SCOPES = {"read", "write", "export", "delete", "manage"}


@dataclass(frozen=True)
class Principal:
    user_id: str
    token_id: str | None
    scopes: tuple[str, ...]


def _hash_token(token: str) -> str:
    pepper = get_settings().auth_token_pepper
    return hashlib.sha256(f"{pepper}:{token}".encode()).hexdigest()


async def create_access_token(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    scopes: list[str],
) -> tuple[AccessToken, str]:
    invalid = set(scopes) - ALLOWED_SCOPES
    if invalid:
        raise ValueError(f"Unsupported scopes: {', '.join(sorted(invalid))}")
    raw_token = f"cl_{secrets.token_urlsafe(32)}"
    record = AccessToken(
        user_id=user_id,
        name=name,
        token_hash=_hash_token(raw_token),
        scopes=sorted(set(scopes)),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record, raw_token


async def verify_access_token(
    session: AsyncSession, raw_token: str
) -> AccessToken | None:
    return await session.scalar(
        select(AccessToken).where(
            AccessToken.token_hash == _hash_token(raw_token),
            AccessToken.active.is_(True),
        )
    )


async def authorize_user(
    session: AsyncSession,
    *,
    user_id: str,
    authorization: str | None,
    required_scope: str,
) -> Principal:
    settings = get_settings()
    mode = settings.auth_mode.lower()
    if mode == "disabled" or (mode == "optional" and not authorization):
        return Principal(user_id=user_id, token_id=None, scopes=("*",))
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A Bearer token is required")
    raw_token = authorization.removeprefix("Bearer ").strip()
    record = await verify_access_token(session, raw_token)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked access token")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Token cannot access another user")
    if required_scope not in record.scopes and "manage" not in record.scopes:
        raise HTTPException(status_code=403, detail=f"Missing required scope: {required_scope}")
    record.last_used_at = datetime.now(UTC)
    await session.flush()
    return Principal(user_id=user_id, token_id=record.id, scopes=tuple(record.scopes))
