"""Multi-agent teams and durable schedules (M6/M8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.runtime.agent import multi
from app.runtime.agent import schedule as schedule_service
from app.schemas.agent_multi import (
    ScheduleCreate,
    ScheduleOccurrenceRead,
    ScheduleRead,
    ScheduleStateUpdate,
    TaskRead,
    TeamCreate,
    TeamMailCreate,
    TeamMailRead,
)
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


async def _authorize(session: AsyncSession, user_id: str, authorization: str | None, scope: str):
    return await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope=scope, touch=False
    )


@router.post("/agent/teams", status_code=201)
async def create_team(
    payload: TeamCreate, session: Session, authorization: Authorization = None
):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    try:
        parent, _children = await multi.create_team(
            session,
            user_id=payload.user_id,
            workspace_id=payload.workspace_id,
            title=payload.title,
            inputs=[item.model_dump() for item in payload.children],
            token_id=principal.token_id,
            budget={"max_turns": payload.max_turns},
        )
    except multi.MultiAgentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        if type(exc).__name__ == "RunAccessRevoked":
            raise HTTPException(403, "Run permission was revoked") from exc
        raise
    await session.commit()
    return {"team_id": parent.team_id, "parent_task_id": parent.id}


@router.get("/agent/teams/{team_id}/tasks", response_model=list[TaskRead])
async def list_team_tasks(
    team_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await multi.list_team_tasks(session, user_id=user_id, team_id=team_id)


@router.get("/agent/tasks/{task_id}", response_model=TaskRead)
async def read_task(
    task_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    task = await multi.get_task(session, user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/agent/tasks/{task_id}/projection")
async def project_task(
    task_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    task = await multi.get_task(session, user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return await multi.project_result(session, user_id=user_id, task=task)


@router.post("/agent/tasks/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "write")
    task = await multi.cancel_task_tree(session, user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    await session.commit()
    return task


@router.post("/agent/teams/{team_id}/messages", response_model=TeamMailRead, status_code=201)
async def append_mail(
    team_id: str,
    payload: TeamMailCreate,
    session: Session,
    authorization: Authorization = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        message = await multi.append_mail(
            session,
            user_id=payload.user_id,
            team_id=team_id,
            message_key=idempotency_key or payload.message_key,
            payload=payload.payload,
            citations=payload.citations,
            recipient_task_id=payload.recipient_task_id,
        )
    except multi.MultiAgentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return message


@router.get("/agent/teams/{team_id}/messages", response_model=list[TeamMailRead])
async def read_mail(
    team_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    recipient_task_id: Annotated[str | None, Query()] = None,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await multi.read_mail(
        session, user_id=user_id, team_id=team_id, recipient_task_id=recipient_task_id
    )


@router.post("/agent/schedules", response_model=ScheduleRead, status_code=201)
async def create_schedule(
    payload: ScheduleCreate, session: Session, authorization: Authorization = None
):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    try:
        record = await schedule_service.create_schedule(
            session,
            user_id=payload.user_id,
            workspace_id=payload.workspace_id,
            name=payload.name,
            prompt=payload.prompt,
            interval_seconds=payload.interval_seconds,
            misfire_policy=payload.misfire_policy,
            actor_token_id=principal.token_id,
            start_at=payload.start_at,
        )
    except schedule_service.ScheduleConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return record


@router.get("/agent/schedules", response_model=list[ScheduleRead])
async def list_schedules(
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await schedule_service.list_schedules(session, user_id=user_id)


@router.post("/agent/schedules/{schedule_id}/state", response_model=ScheduleRead)
async def update_schedule_state(
    schedule_id: str,
    payload: ScheduleStateUpdate,
    session: Session,
    authorization: Authorization = None,
):
    await _authorize(session, payload.user_id, authorization, "write")
    try:
        record = await schedule_service.set_state(
            session, user_id=payload.user_id, schedule_id=schedule_id, state=payload.state
        )
    except schedule_service.ScheduleConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if record is None:
        raise HTTPException(404, "Schedule not found")
    await session.commit()
    return record


@router.post("/agent/schedules/{schedule_id}/trigger", response_model=ScheduleOccurrenceRead)
async def trigger_schedule(
    schedule_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    now: Annotated[int | None, Query()] = None,
    authorization: Authorization = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    await _authorize(session, user_id, authorization, "write")
    moment = now if now is not None else schedule_service.now_seconds()
    if idempotency_key and idempotency_key.isdigit():
        moment = int(idempotency_key)
    try:
        occurrence = await schedule_service.trigger(
            session, user_id=user_id, schedule_id=schedule_id, now=moment, manual=True
        )
    except schedule_service.ScheduleConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if occurrence is None:
        raise HTTPException(404, "Schedule not found")
    await session.commit()
    return occurrence


@router.get(
    "/agent/schedules/{schedule_id}/occurrences", response_model=list[ScheduleOccurrenceRead]
)
async def list_occurrences(
    schedule_id: str,
    session: Session,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    return await schedule_service.list_occurrences(
        session, user_id=user_id, schedule_id=schedule_id
    )
