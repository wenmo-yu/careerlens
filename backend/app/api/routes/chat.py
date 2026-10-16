from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.graph.career import run_career_graph
from app.models.conversation import ConversationThread
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.schemas.chat import ChatRequest, ChatResponse
from app.security import authorize_user
from app.services.profile import read_profile

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


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
    evidence_result = await session.scalars(
        select(Evidence).where(Evidence.user_id == payload.user_id)
    )
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
    thread = None
    if payload.thread_id:
        thread = await session.scalar(
            select(ConversationThread).where(
                ConversationThread.thread_id == payload.thread_id
            )
        )
        if thread is not None and thread.user_id != payload.user_id:
            raise HTTPException(status_code=403, detail="Thread belongs to another user")
    result = await run_career_graph(
        user_id=payload.user_id,
        message=payload.message,
        profile=profile,
        evidence=list(evidence_result),
        job_analysis=analysis,
        thread_id=payload.thread_id,
    )
    if thread is None:
        session.add(
            ConversationThread(user_id=payload.user_id, thread_id=result["thread_id"])
        )
    else:
        thread.updated_at = datetime.now(UTC)
    await session.commit()
    return ChatResponse(
        thread_id=result["thread_id"],
        intent=result["intent"],
        answer=result["answer"],
        evidence=result.get("retrieved_evidence", []),
        retrieval=result.get("retrieval_diagnostics", {}),
        model=result.get("model_diagnostics", {}),
    )
