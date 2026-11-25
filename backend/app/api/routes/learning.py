"""HY4-C: saved JD comparison and learning progress tracking.

Saved JDs are raw user text, never Evidence. Progress can only attach existing
Evidence IDs; it never creates a new capability fact.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.evidence import Evidence
from app.models.learning import LearningProgress, SavedJob
from app.security import authorize_user

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]

ALLOWED_STATUS = {"待开始", "进行中", "待提交作品", "已核对", "暂停"}


class SavedJobCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    jd_text: str = Field(min_length=1, max_length=40000)
    source_type: str = Field(default="pasted", max_length=30)
    source_url: str | None = Field(default=None, max_length=1000)
    notes: str = Field(default="", max_length=4000)


class SavedJobRead(BaseModel):
    id: str
    title: str
    jd_text: str
    source_type: str
    source_url: str | None
    notes: str
    created_at: str

    model_config = {"from_attributes": True}


class ProgressCreate(BaseModel):
    skill: str = Field(min_length=1, max_length=255)
    stage: int = Field(default=1, ge=1, le=50)
    status: str = Field(default="待开始", max_length=30)
    evidence_ids: list[str] = Field(default_factory=list)
    actual_hours: int = Field(default=0, ge=0, le=10000)
    note: str = Field(default="", max_length=2000)


@router.post("/saved-jobs", response_model=SavedJobRead)
async def save_job(
    payload: SavedJobCreate,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> SavedJobRead:
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    source_hash = hashlib.sha256(
        f"{payload.title.strip().lower()}\n{payload.jd_text.strip()}".encode()
    ).hexdigest()
    existing = (
        await session.scalars(
            select(SavedJob).where(
                SavedJob.user_id == payload.user_id, SavedJob.source_hash == source_hash
            )
        )
    ).first()
    if existing is not None:
        existing.notes = payload.notes
        await session.commit()
        await session.refresh(existing)
        return SavedJobRead(
            id=existing.id, title=existing.title, jd_text=existing.jd_text,
            source_type=existing.source_type, source_url=existing.source_url,
            notes=existing.notes, created_at=existing.created_at.isoformat(),
        )
    record = SavedJob(
        user_id=payload.user_id, title=payload.title, jd_text=payload.jd_text,
        source_type=payload.source_type, source_url=payload.source_url,
        source_hash=source_hash, notes=payload.notes,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return SavedJobRead(
        id=record.id, title=record.title, jd_text=record.jd_text,
        source_type=record.source_type, source_url=record.source_url,
        notes=record.notes, created_at=record.created_at.isoformat(),
    )


@router.get("/saved-jobs", response_model=list[SavedJobRead])
async def list_saved_jobs(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> list[SavedJobRead]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(SavedJob).where(SavedJob.user_id == user_id).order_by(SavedJob.created_at.desc())
    )
    return [SavedJobRead(
        id=row.id, title=row.title, jd_text=row.jd_text, source_type=row.source_type,
        source_url=row.source_url, notes=row.notes, created_at=row.created_at.isoformat(),
    ) for row in rows]


@router.delete("/saved-jobs/{job_id}")
async def delete_saved_job(
    job_id: str,
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    record = await session.get(SavedJob, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Saved job not found")
    await authorize_user(
        session, user_id=record.user_id, authorization=authorization, required_scope="write"
    )
    await session.delete(record)
    await session.commit()
    return {"deleted": True, "id": job_id}


@router.get("/saved-jobs/compare")
async def compare_saved_jobs(
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = list(await session.scalars(
        select(SavedJob)
        .where(SavedJob.user_id == user_id)
        .order_by(SavedJob.created_at.desc())
        .limit(3)
    ))
    return {
        "count": len(rows),
        "jobs": [{"id": row.id, "title": row.title, "jd_text": row.jd_text,
                  "source_url": row.source_url, "notes": row.notes} for row in rows],
        "note": (
            "仅保存用户提供的 JD 原句与更正；"
            "规则分需对每份 JD 分别运行岗位分析，勿把重复要求算两次。"
        ),
    }


@router.get("/learning/plans/{plan_id}")
async def get_learning_plan(
    plan_id: str,
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(LearningProgress).where(
            LearningProgress.user_id == user_id, LearningProgress.plan_id == plan_id
        ).order_by(LearningProgress.stage)
    )
    return {"plan_id": plan_id, "items": [{
        "skill": row.skill, "stage": row.stage, "status": row.status,
        "evidence_ids": row.evidence_ids, "actual_hours": row.actual_hours, "note": row.note,
    } for row in rows]}


@router.post("/learning/plans/{plan_id}/progress")
async def upsert_progress(
    plan_id: str,
    payload: ProgressCreate,
    user_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    if payload.status not in ALLOWED_STATUS:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUS)}"
        )
    if payload.evidence_ids:
        found = set(await session.scalars(
            select(Evidence.id).where(
                Evidence.user_id == user_id, Evidence.id.in_(payload.evidence_ids)
            )
        ))
        if not set(payload.evidence_ids) <= found:
            raise HTTPException(
                status_code=422, detail="Progress may only reference your own existing Evidence"
            )
    existing = (
        await session.scalars(
            select(LearningProgress).where(
                LearningProgress.user_id == user_id, LearningProgress.plan_id == plan_id,
                LearningProgress.skill == payload.skill, LearningProgress.stage == payload.stage,
            )
        )
    ).first()
    if existing is None:
        existing = LearningProgress(
            user_id=user_id, plan_id=plan_id, skill=payload.skill, stage=payload.stage,
        )
        session.add(existing)
    existing.status = payload.status
    existing.evidence_ids = list(payload.evidence_ids)
    existing.actual_hours = payload.actual_hours
    existing.note = payload.note
    await session.commit()
    return {"skill": existing.skill, "stage": existing.stage, "status": existing.status}
