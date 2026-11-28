"""M8 MCP connector admission API. Registers and checks policy only; never executes tools."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.runtime.agent import mcp_connectors as connector_service
from app.schemas.mcp_connector import (
    AdmissionCheck,
    AdmissionResult,
    ConnectorAction,
    ConnectorCreate,
    ConnectorRead,
    ConnectorStateUpdate,
    RevokeRead,
)
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.post("/agent/mcp/connectors", response_model=ConnectorRead, status_code=201)
async def register_connector(
    payload: ConnectorCreate, session: Session, authorization: Authorization = None
):
    await _authorize(session, payload.user_id, authorization, "manage")
    try:
        return await connector_service.register(
            session,
            user_id=payload.user_id,
            workspace_id=payload.workspace_id,
            namespace=payload.namespace,
            allowed_tools=payload.allowed_tools,
            required_scope=payload.required_scope,
        )
    except connector_service.ConnectorConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/agent/mcp/connectors", response_model=list[ConnectorRead])
async def list_connectors(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await connector_service.list_connectors(session, user_id=user_id)


@router.post("/agent/mcp/connectors/{connector_id}/state", response_model=ConnectorRead)
async def set_connector_state(
    connector_id: str,
    payload: ConnectorStateUpdate,
    session: Session,
    authorization: Authorization = None,
):
    await _authorize(session, payload.user_id, authorization, "manage")
    try:
        record = await connector_service.set_state(
            session, user_id=payload.user_id, connector_id=connector_id, state=payload.state
        )
    except connector_service.ConnectorConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "Connector not found")
    await session.commit()
    return record


@router.post("/agent/mcp/connectors/{connector_id}/revoke", response_model=RevokeRead)
async def revoke_connector(
    connector_id: str,
    payload: ConnectorAction,
    session: Session,
    authorization: Authorization = None,
):
    await _authorize(session, payload.user_id, authorization, "manage")
    record = await connector_service.revoke(
        session, user_id=payload.user_id, connector_id=connector_id
    )
    if record is None:
        raise HTTPException(404, "Connector not found")
    await session.commit()
    return {"revoked": record.revoked, "state": record.state}


@router.post("/agent/mcp/connectors/{connector_id}/admit", response_model=AdmissionResult)
async def check_admission(
    connector_id: str,
    payload: AdmissionCheck,
    session: Session,
    authorization: Authorization = None,
):
    """Dry-run admission check. Returns a decision; never executes a tool."""

    principal = await _authorize(session, payload.user_id, authorization, "read")
    record = await connector_service.get_connector(
        session, user_id=payload.user_id, connector_id=connector_id
    )
    if record is None:
        raise HTTPException(404, "Connector not found")
    allowed, reason = connector_service.admit(
        record,
        qualified_name=payload.qualified_name,
        caller_scopes=principal.scopes,
        config_digest_supplied=payload.config_digest,
    )
    return {"allowed": allowed, "reason": reason}
