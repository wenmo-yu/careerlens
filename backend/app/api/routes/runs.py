import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.config import get_settings
from app.core.database import get_session
from app.ingestion.contract import source_fingerprint
from app.models.run import TERMINAL, AgentRun, RunEvent, RunStep
from app.runtime import store
from app.schemas.run import EventRead, RunCreate, RunDecision, RunRead, StartWiki, StepRead
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


async def _submit(session: AsyncSession, **values) -> JSONResponse:
    try:
        run, created = await store.submit(session, **values)
    except store.RunConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except store.RunQuota as exc:
        raise HTTPException(429, str(exc)) from exc
    except store.RunAccessRevoked as exc:
        raise HTTPException(403, "Run permission was revoked") from exc
    response = RunRead.model_validate(run)
    await session.commit()
    return JSONResponse(
        status_code=202 if created else 200, content=response.model_dump(mode="json")
    )


@router.post("", response_model=RunRead, status_code=202)
async def start_run(
    payload: RunCreate, session: Session,
    authorization: Authorization = None, idempotency_key: Idempotency = None,
):
    principal = await _authorize(session, payload.user_id, authorization, "write")
    target = f"wiki:{payload.input.slug}" if isinstance(payload, StartWiki) else None
    return await _submit(
        session, user_id=payload.user_id, token_id=principal.token_id,
        request_key=idempotency_key or str(uuid4()), operation=payload.operation,
        payload=payload.input.model_dump(), confirmation=payload.requires_confirmation,
        target=target,
    )


@router.post("/uploads", response_model=RunRead, status_code=202)
async def upload_run(
    session: Session,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    upload: Annotated[UploadFile, File()],
    media: Annotated[bool, Form()] = False,
    requires_confirmation: Annotated[bool, Form()] = False,
    authorization: Authorization = None,
    idempotency_key: Idempotency = None,
):
    principal = await _authorize(session, user_id, authorization, "write")
    settings = get_settings()
    limit = min(
        settings.run_upload_max_bytes,
        settings.media_upload_max_bytes if media else settings.upload_max_bytes,
    )
    try:
        content = await upload.read(limit + 1)
    finally:
        await upload.close()
    if not content:
        raise HTTPException(422, "File is empty")
    if len(content) > limit:
        raise HTTPException(413, "File exceeds the background upload limit")
    filename = (upload.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][-255:]
    fingerprint = source_fingerprint(content)
    return await _submit(
        session, user_id=user_id, token_id=principal.token_id,
        request_key=idempotency_key or str(uuid4()),
        operation="media_import" if media else "file_import",
        payload={
            "filename": filename, "file_size": len(content), "source_hash": fingerprint,
            "source_type": "personal_media" if media else "resume",
            "mime_type": (upload.content_type or "")[:100] or None,
        },
        upload=content, confirmation=requires_confirmation,
        target=f"upload:{fingerprint}",
    )


@router.get("", response_model=list[RunRead])
async def list_runs(
    session: Session, user_id: User, authorization: Authorization = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    await _authorize(session, user_id, authorization, "read")
    return list(await session.scalars(
        select(AgentRun).where(AgentRun.user_id == user_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit)
    ))


async def _get(session: AsyncSession, user_id: str, run_id: str) -> AgentRun:
    run = await store.get_run(session, user_id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/{run_id}", response_model=RunRead)
async def read_run(
    run_id: str, session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    return await _get(session, user_id, run_id)


@router.get("/{run_id}/steps", response_model=list[StepRead])
async def read_steps(
    run_id: str, session: Session, user_id: User, authorization: Authorization = None
):
    await _authorize(session, user_id, authorization, "read")
    await _get(session, user_id, run_id)
    return list(await session.scalars(
        select(RunStep).where(RunStep.run_id == run_id, RunStep.user_id == user_id)
        .order_by(RunStep.updated_at, RunStep.name)
    ))


async def _events(session: AsyncSession, user_id: str, run_id: str, after_seq: int):
    return list(await session.scalars(
        select(RunEvent).where(
            RunEvent.run_id == run_id, RunEvent.user_id == user_id, RunEvent.seq > after_seq
        ).order_by(RunEvent.seq).limit(100)
    ))


@router.get("/{run_id}/events", response_model=list[EventRead])
async def read_events(
    run_id: str, session: Session, user_id: User,
    after_seq: Annotated[int, Query(ge=0)] = 0, authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    await _get(session, user_id, run_id)
    return await _events(session, user_id, run_id, after_seq)


@router.get("/{run_id}/stream")
async def stream_events(
    request: Request, run_id: str, session: Session, user_id: User,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(max_length=15)] = None,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "read")
    run = await _get(session, user_id, run_id)
    if last_event_id is not None:
        if not last_event_id.isascii() or not last_event_id.isdecimal():
            raise HTTPException(400, "Invalid Last-Event-ID")
        after_seq = max(after_seq, int(last_event_id))
    if after_seq > run.event_seq:
        raise HTTPException(409, "Event cursor is ahead of this run")
    await session.rollback()

    async def generate() -> AsyncIterator[str]:
        cursor = after_seq
        idle_ticks = 0
        while not await request.is_disconnected():
            try:
                await _authorize(session, user_id, authorization, "read")
                latest = await session.scalar(
                    select(AgentRun).options(load_only(AgentRun.status, AgentRun.event_seq))
                    .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
                )
                if latest is None:
                    return
                rows = await _events(session, user_id, run_id, cursor)
                terminal, last_seq = latest.status in TERMINAL, latest.event_seq
                messages = [
                    (row.seq, EventRead.model_validate(row).model_dump_json()) for row in rows
                ]
            except HTTPException:
                return
            finally:
                await session.rollback()
            for sequence, data in messages:
                cursor = sequence
                yield f"id: {sequence}\nevent: run\ndata: {data}\n\n"
            if terminal and cursor >= last_seq:
                return
            idle_ticks = 0 if messages else idle_ticks + 1
            if idle_ticks % 20 == 1 and not messages:
                yield ": heartbeat\n\n"
            if len(messages) < 100:
                await asyncio.sleep(0.75)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    run_id: str, session: Session, user_id: User, authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "write")
    run = await store.cancel(session, user_id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    await session.commit()
    return run


@router.post("/{run_id}/decision", response_model=RunRead)
async def decide_run(
    run_id: str, decision: RunDecision, session: Session, user_id: User,
    authorization: Authorization = None,
):
    await _authorize(session, user_id, authorization, "write")
    try:
        run = await store.decide(session, user_id, run_id, decision.approve)
    except store.RunConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if run is None:
        raise HTTPException(404, "Run not found")
    await session.commit()
    return run
