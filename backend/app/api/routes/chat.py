from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.graph.career import run_career_graph
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.runtime.store import read_scope, scope
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
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(80)
    )
    return list(reversed(list(result)))


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: Session,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ChatResponse:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="read",
        touch=False,
    )
    epoch = await read_scope(session, payload.user_id)
    profile = await read_profile(session, payload.user_id)
    if not profile:
        raise HTTPException(status_code=422, detail="Build the user profile before chatting")
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
    if analysis is not None:
        refs = {ref for item in profile for ref in item.evidence_ids}
        live_ids = set(await session.scalars(select(Evidence.id).where(
            Evidence.user_id == payload.user_id, Evidence.id.in_(refs),
        )))
        if not job_analysis_is_current(analysis, profile, live_ids):
            if payload.job_analysis_id:
                raise HTTPException(
                    status_code=409, detail="Job analysis is out of date. Analyze the JD again."
                )
            analysis = None
    thread = None
    turn_version = 0
    if payload.thread_id:
        thread = await session.scalar(
            select(ConversationThread).where(
                ConversationThread.thread_id == payload.thread_id
            )
        )
        if thread is None:
            raise HTTPException(status_code=404, detail="Conversation thread not found")
        if thread.user_id != payload.user_id:
            raise HTTPException(status_code=403, detail="Thread belongs to another user")
        turn_version = await read_scope(session, payload.user_id, f"chat:{thread.thread_id}")

    prior_messages = await _load_history(session, payload.user_id, payload.thread_id)
    history = [
        {"role": item.role, "content": item.content} for item in prior_messages
    ]
    result = await run_career_graph(
        user_id=payload.user_id,
        message=payload.message,
        profile=profile,
        evidence=None,
        job_analysis=analysis,
        thread_id=payload.thread_id,
        history=history,
        session=session,
        mode=payload.mode,
        graph=getattr(request.app.state, "career_graph", None),
    )
    thread_id = result["thread_id"]
    if await scope(session, payload.user_id) != epoch:
        raise HTTPException(status_code=409, detail="Evidence changed during this chat turn")
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="read",
        touch=False,
    )
    if await scope(session, payload.user_id, f"chat:{thread_id}", bump=True) != turn_version + 1:
        raise HTTPException(status_code=409, detail="A newer chat turn has already completed")
    evidence_ids = {
        ref for item in result.get("retrieved_evidence", [])
        for ref in (item.get("evidence_id"), *(item.get("chunk_refs") or []))
        if isinstance(ref, str)
    }
    unknown_lineage = False
    if result.get("intent") != "memory_update" and not result.get("clarification"):
        evidence_ids.update(
            ref for item in result.get("profile", []) for ref in item["evidence_ids"]
        )
        if result.get("intent") == "skill_gap" and analysis is not None:
            evidence_ids.update(ref for item in analysis.matches for ref in item["evidence_ids"])
        if result.get("model_diagnostics", {}).get("provider") not in {"demo", "workflow"}:
            for message in prior_messages[-6:]:
                if message.role != "assistant":
                    continue
                if not isinstance(message.evidence_ids, list):
                    unknown_lineage = True
                else:
                    evidence_ids.update(ref for ref in message.evidence_ids if isinstance(ref, str))

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
            evidence_ids=[],
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
            evidence_ids=None if unknown_lineage else sorted(evidence_ids),
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
