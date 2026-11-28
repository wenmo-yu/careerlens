"""Public agent API: sessions, turns, approvals and runtime diagnostics.

The API owns durable state. It never runs the loop; it records the turn and
returns 202, then the scheduler drives a CLI and commits the outcome.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.models.agent import AgentApproval, AgentArtifact, AgentRuntimeSlot
from app.models.run import AgentRun
from app.runtime import heartbeat
from app.runtime.agent import roles as role_service
from app.runtime.agent import store, tools
from app.schemas.agent import (
    ApprovalDecision,
    ApprovalRead,
    ArtifactRead,
    MessageRead,
    SessionCreate,
    SessionRead,
    TurnCreate,
)
from app.schemas.run import RunRead
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
User = Annotated[str, Query(min_length=1, max_length=128)]
Authorization = Annotated[str | None, Header()]
Idempotency = Annotated[str | None, Header(min_length=1, max_length=128)]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.post("/agent/sessions", response_model=SessionRead, status_code=201)
async def create_session(
    payload: SessionCreate, session: Session, authorization: Authorization = None
):
    await _authorize(session, payload.user_id, authorization, "write")
    record = await store.create_session(
        session,
        user_id=payload.user_id,
        title=payload.title,
        workspace_id=payload.workspace_id,
    )
    await session.commit()
    return record


@router.get("/agent/sessions", response_model=list[SessionRead])
async def list_sessions(
    session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    return await store.list_sessions(session, user_id)


@router.get("/agent/sessions/{session_id}", response_model=SessionRead)
async def read_session(
    session_id: str, session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    record = await store.get_session(session, user_id, session_id)
    if record is None:
        raise HTTPException(404, "Session not found")
    return record


@router.get("/agent/sessions/{session_id}/messages", response_model=list[MessageRead])
async def read_messages(
    session_id: str,
    session: Session,
    user_id: User,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    if await store.get_session(session, user_id, session_id) is None:
        raise HTTPException(404, "Session not found")
    return await store.read_messages(
        session, user_id=user_id, session_id=session_id, after_seq=after_seq
    )


@router.post("/agent/sessions/{session_id}/runs", response_model=RunRead, status_code=202)
async def submit_turn(
    session_id: str,
    payload: TurnCreate,
    session: Session,
    authorization: Authorization = None,
    idempotency_key: Idempotency = None,
):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    try:
        run, created = await store.submit_turn(
            session,
            user_id=payload.user_id,
            session_id=session_id,
            text=payload.text,
            token_id=principal.token_id,
            request_key=idempotency_key or str(uuid4()),
        )
    except store.AgentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except store.RunAccessRevoked as exc:
        raise HTTPException(403, "Run permission was revoked") from exc
    data = RunRead.model_validate(run).model_dump(mode="json")
    await session.commit()
    return JSONResponse(status_code=202 if created else 200, content=data)


@router.get("/agent/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    return await store.pending_approvals(session, user_id=user_id)


@router.post("/agent/approvals/{run_id}/decision", response_model=RunRead)
async def decide_approval(
    run_id: str,
    payload: ApprovalDecision,
    session: Session,
    authorization: Authorization = None,
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        run = await store.decide_approval(
            session, user_id=payload.user_id, run_id=run_id, approve=payload.approve
        )
    except store.AgentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if run is None:
        raise HTTPException(404, "Run not found")
    await session.commit()
    return run


@router.get("/agent/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(
    session: Session,
    user_id: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return list(
        await session.scalars(
            select(AgentArtifact)
            .where(AgentArtifact.user_id == user_id)
            .order_by(AgentArtifact.created_at.desc(), AgentArtifact.id.desc())
            .limit(limit)
        )
    )


@router.get("/agent/artifacts/{artifact_id}", response_model=ArtifactRead)
async def read_artifact(
    artifact_id: str,
    session: Session,
    user_id: User,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    artifact = await session.scalar(
        select(AgentArtifact).where(
            AgentArtifact.id == artifact_id, AgentArtifact.user_id == user_id
        )
    )
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return artifact


@router.get("/runtime/capabilities")
async def runtime_capabilities(
    session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    settings = get_settings()
    return {
        "protocol": 1,
        "agent_runtime_enabled": settings.agent_runtime_enabled,
        "executor_kinds": ["workflow", "agent"],
        "model_provider": settings.agent_model_provider,
        "limits": {
            "max_running": settings.agent_max_running,
            "warm_target": settings.agent_warm_target,
            "warm_max": settings.agent_warm_max,
            "total_process_cap": settings.agent_total_cap,
            "lease_seconds": settings.agent_lease_seconds,
            "turn_timeout_seconds": settings.agent_turn_timeout_seconds,
        },
        "read_only_tools": tools.read_tools(),
        "write_tools": tools.write_tools(),
        "tool_ledger": True,
        "roles": {
            "enabled": True,
            "templates": sorted(role_service.ROLE_TEMPLATES),
            "tool_narrowing": True,
        },
    }


@router.get("/runtime/status")
async def runtime_status(
    session: Session, user_id: User, authorization: Authorization = None
):
    """Pool and admission diagnostics from durable state (no daemon IPC needed)."""

    await _authorize(session, user_id, authorization, "read")
    slots = list(
        await session.execute(
            select(AgentRuntimeSlot.state, func.count())
            .group_by(AgentRuntimeSlot.state)
        )
    )
    runs = list(
        await session.execute(
            select(AgentRun.status, func.count())
            .where(AgentRun.executor_kind == "agent")
            .group_by(AgentRun.status)
        )
    )
    approvals = await session.scalar(
        select(func.count())
        .select_from(AgentApproval)
        .where(AgentApproval.status == "pending")
    )
    expired = await session.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.executor_kind == "agent",
            AgentRun.status == "running",
            AgentRun.lease_until.is_not(None),
            AgentRun.lease_until <= int(datetime.now(UTC).timestamp()),
        )
    )
    heartbeats = await heartbeat.read_status(
        session, stale_after_seconds=get_settings().agent_lease_seconds * 3
    )
    return {
        "protocol": 1,
        "slots": {state: count for state, count in slots},
        "runs": {state: count for state, count in runs},
        "pending_approvals": approvals or 0,
        "expired_leases": expired or 0,
        "heartbeats": heartbeats,
        "generated_at": datetime.now(UTC).isoformat(),
    }
