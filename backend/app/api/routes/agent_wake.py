"""M8 wake reconciliation API: explain missed schedules after a liveness gap."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.runtime.agent import wake as wake_service
from app.schemas.wake import WakeReconcileRequest, WakeReportRead
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.post("/agent/wake/reconcile", response_model=WakeReportRead, status_code=201)
async def reconcile_wake(
    payload: WakeReconcileRequest,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    """Operational endpoint: trigger a reconciliation for a liveness gap.

    Scoped to manage, because it enqueues runs. The scheduler can call the
    service directly without HTTP; this route is for diagnostics and operators.
    """
    await _authorize(session, user_id, authorization, "manage")
    try:
        report = await wake_service.reconcile(
            session, last_seen=payload.last_seen, now=payload.now
        )
    except wake_service.WakeConflict as exc:
        raise HTTPException(422, str(exc)) from exc
    await session.commit()
    return report


@router.get("/agent/wake/reports", response_model=list[WakeReportRead])
async def list_wake_reports(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await wake_service.list_reports(session)
