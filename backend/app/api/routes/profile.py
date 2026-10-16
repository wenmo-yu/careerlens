from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.profile_update import ProfileUpdateProposal
from app.schemas.profile import (
    ProfileProposalCreate,
    ProfileProposalDecision,
    ProfileProposalRead,
    ProfileRead,
)
from app.security import authorize_user
from app.services.profile import read_profile, rebuild_profile
from app.services.profile_updates import create_proposal, decide_proposal, list_proposals

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


@router.post("/{user_id}/rebuild", response_model=ProfileRead)
async def rebuild(
    user_id: str, session: Session, authorization: Authorization = None
) -> ProfileRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    try:
        items = await rebuild_profile(session, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProfileRead(user_id=user_id, items=items, count=len(items))


@router.get("/{user_id}", response_model=ProfileRead)
async def get_profile(
    user_id: str, session: Session, authorization: Authorization = None
) -> ProfileRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    items = await read_profile(session, user_id)
    return ProfileRead(user_id=user_id, items=items, count=len(items))


@router.post("/{user_id}/proposals", response_model=ProfileProposalRead)
async def propose_update(
    user_id: str,
    payload: ProfileProposalCreate,
    session: Session,
    authorization: Authorization = None,
) -> ProfileProposalRead:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    return await create_proposal(session, user_id=user_id, message=payload.message)


@router.get("/{user_id}/proposals", response_model=list[ProfileProposalRead])
async def get_proposals(
    user_id: str,
    session: Session,
    status: str | None = None,
    authorization: Authorization = None,
) -> list[ProfileProposalRead]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    return await list_proposals(session, user_id=user_id, status=status)


@router.post("/proposals/{proposal_id}/decision", response_model=ProfileProposalRead)
async def resolve_proposal(
    proposal_id: str,
    payload: ProfileProposalDecision,
    session: Session,
    authorization: Authorization = None,
) -> ProfileProposalRead:
    proposal = await session.get(ProfileUpdateProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Profile update proposal not found")
    await authorize_user(
        session,
        user_id=proposal.user_id,
        authorization=authorization,
        required_scope="write",
    )
    try:
        return await decide_proposal(session, proposal_id=proposal_id, approve=payload.approve)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
