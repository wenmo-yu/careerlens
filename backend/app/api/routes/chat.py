from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.graph.career import run_career_graph
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.security import authorize_user
from app.services.jobs import job_analysis_is_current
from app.services.profile import read_profile

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


async def _load_history(
    session: AsyncSession, user_id: str, thread_id: str | None
) -> list[ConversationMessage]:
    if not thread_id:
        return []
    result = await session.scalars(
        select(ConversationMessage)
        .where(
            ConversationMessage.user_id == user_id,
            ConversationMessage.thread_id == thread_id,
        )
        .order_by(ConversationMessage.created_at, ConversationMessage.id)
    )
    return list(result)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> ChatResponse:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="read",
    )
    profile = await read_profile(session, payload.user_id)
    if not profile:
        raise HTTPException(status_code=422, detail="Build the user profile before chatting")
    evidence = list(await session.scalars(
        select(Evidence).where(Evidence.user_id == payload.user_id)
    ))
    if payload.job_analysis_id:
        analysis = await session.get(JobAnalysis, payload.job_analysis_id)
        if analysis is None or analysis.user_id != payload.user_id:
            raise HTTPException(status_code=404, detail="Job analysis not found for this user")
    else:
        analysis = await session.scalar(
            select(JobAnalysis)
            .where(JobAnalysis.user_id == payload.user_id)
            .order_by(JobAnalysis.created_at.desc(), JobAnalysis.id.desc())
            .limit(1)
        )
    if analysis is not None and not job_analysis_is_current(
        analysis, profile, {record.id for record in evidence}
    ):
        if payload.job_analysis_id:
            raise HTTPException(
                status_code=409, detail="Job analysis is out of date. Analyze the JD again."
            )
        analysis = None
    thread = None
    if payload.thread_id:
        thread = await session.scalar(
            select(ConversationThread).where(
                ConversationThread.thread_id == payload.thread_id
            )
        )
        if thread is not None and thread.user_id != payload.user_id:
            raise HTTPException(status_code=403, detail="Thread belongs to another user")

    prior_messages = await _load_history(session, payload.user_id, payload.thread_id)
    history = [
        {"role": item.role, "content": item.content} for item in prior_messages
    ]
    result = await run_career_graph(
        user_id=payload.user_id,
        message=payload.message,
        profile=profile,
        evidence=evidence,
        job_analysis=analysis,
        thread_id=payload.thread_id,
        history=history,
        session=session,
        mode=payload.mode,
    )
    thread_id = result["thread_id"]

    # Explicit, ordered timestamps: both messages can be flushed in one batch,
    # where a column default may resolve to the same microsecond and leave the
    # turn ordered by random UUID.
    turn_started_at = datetime.now(UTC)
    session.add(
        ConversationMessage(
            user_id=payload.user_id,
            thread_id=thread_id,
            role="user",
            content=payload.message,
            created_at=turn_started_at,
        )
    )
    session.add(
        ConversationMessage(
            user_id=payload.user_id,
            thread_id=thread_id,
            role="assistant",
            content=result["answer"],
            intent=result.get("intent"),
            created_at=turn_started_at + timedelta(microseconds=1),
        )
    )
    if thread is None:
        session.add(
            ConversationThread(user_id=payload.user_id, thread_id=thread_id)
        )
    else:
        thread.updated_at = datetime.now(UTC)
    await session.commit()

    all_messages = await _load_history(session, payload.user_id, thread_id)
    return ChatResponse(
        thread_id=thread_id,
        intent=result["intent"],
        answer=result["answer"],
        evidence=result.get("retrieved_evidence", []),
        retrieval=result.get("retrieval_diagnostics", {}),
        model=result.get("model_diagnostics", {}),
        messages=[
            ChatMessage(
                role=item.role,
                content=item.content,
                intent=item.intent,
                created_at=item.created_at.isoformat() if item.created_at else None,
            )
            for item in all_messages
        ],
    )
