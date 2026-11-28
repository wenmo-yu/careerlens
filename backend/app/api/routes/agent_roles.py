"""M8 durable-role API. Roles are user-configured and never gain tool scope."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.runtime.agent import roles as role_service
from app.runtime.store import RunAccessRevoked
from app.schemas.agent_role import (
    RoleCreate,
    RoleRead,
    RoleStateUpdate,
    RoleTrigger,
    RoleUpdate,
)
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.post("/agent/roles", response_model=RoleRead, status_code=201)
async def create_role(payload: RoleCreate, session: Session, authorization: Authorization = None):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    try:
        return await role_service.create_role(
            session,
            user_id=payload.user_id,
            workspace_id=payload.workspace_id,
            name=payload.name,
            template=payload.template,
            prompt=payload.prompt,
            tool_allowlist=payload.tool_allowlist,
            model_policy=payload.model_policy,
            budget=payload.budget,
            output_schema=payload.output_schema,
            actor_token_id=principal.token_id,
        )
    except role_service.RoleConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/agent/roles", response_model=list[RoleRead])
async def list_roles(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await role_service.list_roles(session, user_id=user_id)


@router.get("/agent/roles/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    record = await role_service.get_role(session, user_id=user_id, role_id=role_id)
    if record is None:
        raise HTTPException(404, "Role not found")
    return record


@router.patch("/agent/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: str, payload: RoleUpdate, session: Session, authorization: Authorization = None
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        record = await role_service.update_role(
            session,
            user_id=payload.user_id,
            role_id=role_id,
            prompt=payload.prompt,
            tool_allowlist=payload.tool_allowlist,
            model_policy=payload.model_policy,
            budget=payload.budget,
            output_schema=payload.output_schema,
        )
    except role_service.RoleConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "Role not found")
    return record


@router.post("/agent/roles/{role_id}/state", response_model=RoleRead)
async def set_role_state(
    role_id: str, payload: RoleStateUpdate, session: Session, authorization: Authorization = None
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        record = await role_service.set_state(
            session, user_id=payload.user_id, role_id=role_id, state=payload.state
        )
    except role_service.RoleConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "Role not found")
    return record


@router.post("/agent/roles/{role_id}/trigger", status_code=202)
async def trigger_role(
    role_id: str,
    payload: RoleTrigger,
    session: Session,
    authorization: Authorization = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    request_key = idempotency_key or f"role-trigger:{role_id}:{payload.text}"
    try:
        record, run, created = await role_service.trigger(
            session,
            user_id=payload.user_id,
            role_id=role_id,
            text=payload.text,
            request_key=request_key,
            actor_token_id=principal.token_id,
        )
    except role_service.RoleConflict as exc:
        code = str(exc)
        status = 404 if "role_not_found" in code else 409
        raise HTTPException(status, code) from exc
    except RunAccessRevoked as exc:
        # A revoked actor pauses the role so repeated triggers cannot run.
        record = await role_service.get_role(
            session, user_id=payload.user_id, role_id=role_id
        )
        if record is not None:
            await role_service.set_state(
                session, user_id=payload.user_id, role_id=role_id, state="paused"
            )
        raise HTTPException(403, "actor_revoked") from exc
    return {
        "role_id": record.id,
        "role_version": record.version,
        "run_id": run.id,
        "session_id": record.session_id,
        "created": created,
    }
