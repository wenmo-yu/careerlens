"""HY4-C: deterministic recommendations grounded in the user's evidence."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.evidence import Evidence
from app.schemas.catalog import LearningPlanStepRead, RoleSuggestionRead
from app.security import authorize_user
from app.services.jobs import job_inputs
from app.services.recommendation import (
    build_learning_plan_v2,
    recommend_courses,
    recommend_roles,
)

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


class RoleRecommendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=5, ge=1, le=10)


class LearningPlanRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    analysis_id: str = Field(min_length=1)
    skill: str | None = None
    weekly_hours: int = Field(default=8, ge=1, le=80)


@router.post("/roles", response_model=list[RoleSuggestionRead])
async def suggest_roles(
    payload: RoleRecommendRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[RoleSuggestionRead]:
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="read"
    )
    try:
        profile, valid_ids = await job_inputs(session, payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evidence = list(
        await session.scalars(
            select(Evidence).where(Evidence.user_id == payload.user_id, Evidence.id.in_(valid_ids))
        )
    ) if valid_ids else []
    rows = recommend_roles(profile, evidence, limit=payload.limit)
    if not rows:
        raise HTTPException(
            status_code=422,
            detail=(
                "No evidenced skills match the local role catalog; "
                "import evidence and rebuild the profile first."
            ),
        )
    return [RoleSuggestionRead(**row) for row in rows]


@router.post("/learning-plan", response_model=list[LearningPlanStepRead])
async def suggest_learning_plan(
    payload: LearningPlanRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[LearningPlanStepRead]:
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="read"
    )
    from app.models.job_analysis import JobAnalysis

    analysis = await session.get(JobAnalysis, payload.analysis_id)
    if analysis is None or analysis.user_id != payload.user_id:
        raise HTTPException(status_code=404, detail="Job analysis not found")
    try:
        profile, valid_ids = await job_inputs(session, payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.skill:
        courses = recommend_courses(payload.skill, weekly_hours=payload.weekly_hours)
        return [LearningPlanStepRead(
            stage=1, skill=payload.skill, priority="optional", current_level=1,
            target_level=2, estimated_hours=sum(row["estimated_hours"] for row in courses),
            start_week=1, weeks=1, goal=f"补齐 {payload.skill}",
            deliverables=[row["verification"] for row in courses],
            source_evidence_ids=[],
            resources=[{"course_id": row["course_id"], "title": row["title"],
                        "url": row["url"], "estimated_hours": row["estimated_hours"],
                        "prerequisites": row["prerequisites"]} for row in courses],
            verification=courses[0]["verification"] if courses else "完成一个可复跑的最小实践。",
            progress_status="待开始",
        )] if courses else []
    steps = build_learning_plan_v2(analysis.learning_path or [], profile, valid_ids)
    return [LearningPlanStepRead(**step) for step in steps]
