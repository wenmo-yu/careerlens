from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.observability import get_metrics_store
from app.security.auth import authorize_ops

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


async def _ops_guard(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Metrics are instance-wide; require a manage-scoped token in secured modes."""
    await authorize_ops(session, authorization=authorization)


@router.get("/summary")
async def observability_summary(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    await _ops_guard(session, authorization)
    return get_metrics_store().summary()


@router.get("/calls")
async def observability_calls(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    await _ops_guard(session, authorization)
    items = get_metrics_store().calls(limit)
    return {"items": items, "count": len(items)}
