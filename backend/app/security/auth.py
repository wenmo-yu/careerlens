import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.access_token import AccessToken
from app.models.run import RunScope

ALLOWED_SCOPES = {"read", "write", "export", "delete", "manage"}
DELETED_ACCOUNT = "account_deleted"


@dataclass(frozen=True)
class Principal:
    user_id: str
    token_id: str | None
    scopes: tuple[str, ...]


def _hash_token(token: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{token}".encode()).hexdigest()


def _token_keys(settings: Settings, now: datetime) -> list[tuple[int, str]]:
    keys = [(settings.auth_token_key_version, settings.auth_token_pepper)]
    if (
        settings.auth_token_previous_pepper
        and settings.auth_token_previous_until is not None
        and now < settings.auth_token_previous_until
    ):
        keys.append((
            settings.auth_token_key_version - 1, settings.auth_token_previous_pepper,
        ))
    return keys


def _active_token(audience: str, now: datetime):
    return (
        AccessToken.active.is_(True),
        AccessToken.audience == audience,
        AccessToken.expires_at > now,
    )


def bearer_value(authorization: str | None) -> str:
    scheme, _, raw = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        raise HTTPException(status_code=401, detail="A Bearer token is required")
    return raw.strip()


def is_ops_token(raw_token: str) -> bool:
    expected = get_settings().ops_access_token
    return bool(expected) and secrets.compare_digest(raw_token.encode(), expected.encode())


async def create_access_token(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    scopes: list[str],
    audience: str = "api",
) -> tuple[AccessToken, str]:
    invalid = set(scopes) - ALLOWED_SCOPES
    if invalid:
        raise ValueError(f"Unsupported scopes: {', '.join(sorted(invalid))}")
    if audience not in {"api", "mcp"}:
        raise ValueError("Unsupported token audience")
    settings = get_settings()
    raw_token = f"cl_{secrets.token_urlsafe(32)}"
    record = AccessToken(
        user_id=user_id,
        name=name,
        token_hash=_hash_token(raw_token, settings.auth_token_pepper),
        scopes=sorted(set(scopes)),
        audience=audience,
        resource=settings.mcp_resource_server_url if audience == "mcp" else None,
        key_version=settings.auth_token_key_version,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.auth_token_lifetime_hours),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record, raw_token


async def verify_access_token(
    session: AsyncSession, raw_token: str, *, audience: str = "api",
    settings: Settings | None = None,
) -> AccessToken | None:
    if not raw_token or len(raw_token) > 256:
        return None
    settings = settings or get_settings()
    now = datetime.now(UTC)
    hashes = [
        and_(AccessToken.key_version == version, AccessToken.token_hash == _hash_token(
            raw_token, pepper,
        ))
        for version, pepper in _token_keys(settings, now)
    ]
    query = select(AccessToken).where(*_active_token(audience, now), or_(*hashes))
    if audience == "mcp":
        query = query.where(AccessToken.resource == settings.mcp_resource_server_url)
    return await session.scalar(query)


async def load_run_token(session: AsyncSession, token_id: str, user_id: str) -> AccessToken | None:
    now = datetime.now(UTC)
    versions = [version for version, _ in _token_keys(get_settings(), now)]
    return await session.scalar(select(AccessToken).where(
        AccessToken.id == token_id,
        AccessToken.user_id == user_id,
        AccessToken.key_version.in_(versions),
        *_active_token("api", now),
    ).execution_options(populate_existing=True))


async def account_was_deleted(session: AsyncSession, user_id: str) -> bool:
    return bool(await session.scalar(select(RunScope.generation).where(
        RunScope.user_id == user_id, RunScope.key == DELETED_ACCOUNT,
    )))


async def authorize_user(
    session: AsyncSession,
    *,
    user_id: str,
    authorization: str | None,
    required_scope: str,
    touch: bool = False,
) -> Principal:
    settings = get_settings()
    mode = settings.auth_mode.lower()
    if mode == "disabled" or (mode == "optional" and not authorization):
        if await account_was_deleted(session, user_id):
            raise HTTPException(status_code=410, detail="This account has been deleted")
        return Principal(user_id=user_id, token_id=None, scopes=("*",))
    record = await verify_access_token(session, bearer_value(authorization))
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid, expired or revoked access token")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Token cannot access another user")
    if await account_was_deleted(session, user_id):
        raise HTTPException(status_code=401, detail="Invalid, expired or revoked access token")
    if required_scope not in record.scopes and "manage" not in record.scopes:
        raise HTTPException(status_code=403, detail=f"Missing required scope: {required_scope}")
    if touch:
        record.last_used_at = datetime.now(UTC)
        await session.flush()
    return Principal(user_id=user_id, token_id=record.id, scopes=tuple(record.scopes))


async def authorize_ops(
    session: AsyncSession,
    *,
    authorization: str | None,
) -> Principal:
    """Global operations use a separate deployment credential."""
    settings = get_settings()
    mode = settings.auth_mode.lower()
    if mode == "disabled" and settings.app_env != "production":
        return Principal(user_id="ops", token_id=None, scopes=("*",))
    raw_token = bearer_value(authorization)
    if is_ops_token(raw_token):
        return Principal(user_id="ops", token_id=None, scopes=("ops",))
    if await verify_access_token(session, raw_token) is not None:
        raise HTTPException(status_code=403, detail="Instance operations access is required")
    raise HTTPException(status_code=401, detail="Invalid operations credential")
