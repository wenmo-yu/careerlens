from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.job_analysis import JobAnalysis
from app.schemas.job import JobAnalysisRead, JobAnalyzeRequest
from app.security import authorize_user
from app.services.jobs import analyze_job

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/analyze", response_model=JobAnalysisRead)
async def create_analysis(
    payload: JobAnalyzeRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> JobAnalysisRead:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="write",
    )
    try:
        return await analyze_job(session, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{analysis_id}", response_model=JobAnalysisRead)
async def get_analysis(
    analysis_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> JobAnalysisRead:
    analysis = await session.get(JobAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Job analysis not found")
    await authorize_user(
        session,
        user_id=analysis.user_id,
        authorization=authorization,
        required_scope="read",
    )
    return JobAnalysisRead.model_validate(analysis)
