"""Internal gateway used by the agent CLI.

Protected by a short-lived capability bound to user/session/run/attempt/
generation. These routes are deliberately excluded from the public OpenAPI
snapshot: the CLI is a local, trusted-by-capability caller, not a public API.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.llm.provider import ModelUnavailable
from app.models.run import AgentRun
from app.runtime.agent import capability as caps
from app.runtime.agent import model, tools

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
CapabilityHeader = Annotated[str | None, Header(alias="X-Agent-Capability")]


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str = ""


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage] = Field(min_length=1, max_length=40)
    tools: list[dict] = Field(default_factory=list, max_length=20)


class ToolInvoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(default=None, max_length=36)
    invocation_id: str | None = Field(default=None, max_length=64)
    approval_id: str | None = Field(default=None, max_length=36)
    approved: bool = False
    args_digest: str | None = Field(default=None, max_length=64)


async def _capability(session: AsyncSession, token: str | None) -> caps.Capability:
    if not token:
        raise HTTPException(401, "Missing agent capability")
    try:
        claim = caps.verify(token)
    except caps.CapabilityError as exc:
        raise HTTPException(401, str(exc)) from exc
    run = await session.get(AgentRun, claim.run_id)
    if (
        run is None
        or run.user_id != claim.user_id
        or run.session_id != claim.session_id
        or run.executor_kind != "agent"
        or run.status != "running"
        or run.attempts != claim.attempt
    ):
        raise HTTPException(409, "Capability no longer matches an active run")
    return claim


@router.post("/internal/agent/model/complete")
async def complete(
    payload: ModelRequest,
    session: Session,
    capability: CapabilityHeader = None,
):
    claim = await _capability(session, capability)
    messages = [message.model_dump() for message in payload.messages]
    allowed = {tool["name"] for tool in tools.definitions()}
    offered = [tool for tool in payload.tools if tool.get("name") in allowed]
    provider = get_settings().agent_model_provider

    async def generate():
        try:
            async for event in model.stream_provider(messages, offered, provider=provider):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ModelUnavailable as exc:
            failure = {"type": "done", "stop_reason": "model_unavailable", "error": exc.reason}
            yield f"data: {json.dumps(failure, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            failure = {"type": "done", "stop_reason": "invalid_request", "error": str(exc)}
            yield f"data: {json.dumps(failure, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Agent-Run": claim.run_id,
        },
    )


@router.post("/internal/agent/tools/invoke")
async def invoke_tool(
    payload: ToolInvoke,
    session: Session,
    capability: CapabilityHeader = None,
):
    claim = await _capability(session, capability)
    try:
        result = await tools.invoke(
            session,
            user_id=claim.user_id,
            name=payload.name,
            args=payload.args,
            run_id=claim.run_id,
            session_id=payload.session_id or "",
            invocation_id=payload.invocation_id,
            approval_id=payload.approval_id,
            approved=payload.approved,
            args_digest=payload.args_digest,
        )
    except tools.ToolRejected as exc:
        if exc.persist:
            await session.commit()
        else:
            await session.rollback()
        return {"ok": False, "code": exc.code, "message": exc.message}
    await session.commit()
    return {"ok": True, "result": result}
