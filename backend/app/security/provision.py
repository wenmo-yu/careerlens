"""Issue a tenant owner credential from a trusted operator shell."""

import argparse
import asyncio

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models.access_token import AccessToken
from app.runtime.store import scope
from app.security.auth import ALLOWED_SCOPES, account_was_deleted, create_access_token


async def provision_owner(session: AsyncSession, user_id: str, *, recover: bool) -> str:
    if not user_id or user_id != user_id.strip() or len(user_id) > 128:
        raise ValueError("Supply a nonempty account ID of at most 128 characters")
    await scope(session, user_id)
    if await account_was_deleted(session, user_id):
        raise ValueError("This account identifier was retired")
    existing = await session.scalar(select(AccessToken.id).where(
        AccessToken.user_id == user_id,
    ).limit(1))
    if bool(existing) != recover:
        raise ValueError("The account already exists" if existing else "The account is unknown")
    if recover:
        await session.execute(update(AccessToken).where(
            AccessToken.user_id == user_id,
        ).values(active=False))
    _, raw = await create_access_token(
        session, user_id=user_id, name="Owner", scopes=sorted(ALLOWED_SCOPES),
    )
    return raw


async def _run(user_id: str, *, recover: bool) -> str:
    get_settings().validate_security("worker")
    async with SessionFactory() as session:
        return await provision_owner(session, user_id, recover=recover)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id")
    parser.add_argument("--recover", action="store_true", help="Revoke and replace existing tokens")
    args = parser.parse_args()
    try:
        raw = asyncio.run(_run(args.user_id, recover=args.recover))
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(raw)


if __name__ == "__main__":
    main()
