"""Self-reported profile extensions: constraints, dimensions, view preferences.

None of these rows become facts about the user. Constraints filter explanations,
dimensions change display and soft ordering, view preferences only choose a
layout, and interview stories must point at the user's own Evidence.
"""

import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.assessment import UserConstraint
from app.models.evidence import Evidence
from app.models.profile_extension import DimensionDefinition, ProfileExtension
from app.runtime.store import check_write_scope
from app.schemas.assessment import (
    ConstraintUpsert,
    DimensionToggle,
    InterviewStory,
    ViewPreferences,
)
from app.security import authorize_user
from app.services.profile_view_preferences import (
    MODE_LABELS,
    MODES,
    default_modules,
    normalise_mode,
)

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]


@router.put("/constraints/me")
async def upsert_constraint(
    payload: ConstraintUpsert,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    await check_write_scope(session, payload.user_id)
    existing = (
        await session.scalars(
            select(UserConstraint).where(
                UserConstraint.user_id == payload.user_id, UserConstraint.kind == payload.kind
            )
        )
    ).first()
    if existing is None:
        existing = UserConstraint(user_id=payload.user_id, kind=payload.kind, value=payload.value)
        session.add(existing)
    existing.value = payload.value
    existing.strength = payload.strength
    await session.commit()
    return {"kind": existing.kind, "value": existing.value, "strength": existing.strength}


@router.get("/constraints/me")
async def list_constraints(
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> list[dict]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(UserConstraint).where(UserConstraint.user_id == user_id)
    )
    return [{"kind": row.kind, "value": row.value, "strength": row.strength} for row in rows]


@router.get("/profiles/{user_id}/dimensions")
async def list_dimensions(
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    definitions = await session.scalars(
        select(DimensionDefinition).where(DimensionDefinition.user_id == user_id)
    )
    extensions = await session.scalars(
        select(ProfileExtension).where(ProfileExtension.user_id == user_id)
    )
    values = {row.dimension_key: row for row in extensions}
    return {
        "dimensions": [{
            "key": row.key, "label": row.label, "description": row.description,
            "enabled": row.enabled, "source": row.source,
            "value": values[row.key].value_json if row.key in values else None,
            "evidence_ids": values[row.key].evidence_ids if row.key in values else [],
        } for row in definitions],
        "note": "自定义维度不进入岗位匹配分；启用/停用只改变展示与软排序。",
    }


@router.put("/profiles/{user_id}/dimensions")
async def toggle_dimension(
    user_id: str,
    payload: DimensionToggle,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    await check_write_scope(session, user_id)
    if payload.evidence_ids:
        found = set(await session.scalars(
            select(Evidence.id).where(
                Evidence.user_id == user_id, Evidence.id.in_(payload.evidence_ids)
            )
        ))
        if not set(payload.evidence_ids) <= found:
            raise HTTPException(
                status_code=422, detail="Dimension may only reference your own Evidence"
            )
    definition = (
        await session.scalars(
            select(DimensionDefinition).where(
                DimensionDefinition.user_id == user_id, DimensionDefinition.key == payload.key
            )
        )
    ).first()
    if definition is None:
        definition = DimensionDefinition(user_id=user_id, key=payload.key, label=payload.label)
        session.add(definition)
    definition.label = payload.label
    definition.description = payload.description
    definition.enabled = payload.enabled
    if payload.value is not None:
        extension = (
            await session.scalars(
                select(ProfileExtension).where(
                    ProfileExtension.user_id == user_id,
                    ProfileExtension.dimension_key == payload.key,
                )
            )
        ).first()
        if extension is None:
            extension = ProfileExtension(
                user_id=user_id, dimension_key=payload.key, value_json=payload.value,
                evidence_ids=payload.evidence_ids,
            )
            session.add(extension)
        extension.value_json = payload.value
        extension.evidence_ids = list(payload.evidence_ids)
        extension.enabled = payload.enabled
    elif not payload.enabled:
        await session.execute(
            delete(ProfileExtension).where(
                ProfileExtension.user_id == user_id,
                ProfileExtension.dimension_key == payload.key,
            )
        )
    await session.commit()
    return {"key": payload.key, "enabled": payload.enabled}


@router.get("/profiles/{user_id}/view-preferences")
async def get_view_preferences(
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    """Read display mode and module switches. Pure preference; no facts change."""
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(UserConstraint).where(
            UserConstraint.user_id == user_id,
            UserConstraint.kind.in_(("profile_mode", "profile_modules")),
        )
    )
    values = {row.kind: row.value for row in rows}
    modules = default_modules()
    if "profile_modules" in values:
        try:
            stored = json.loads(values["profile_modules"])
            if isinstance(stored, dict):
                for key in list(modules):
                    if key in stored and isinstance(stored[key], bool):
                        modules[key] = stored[key]
        except (ValueError, TypeError):
            pass
    mode = normalise_mode(values.get("profile_mode"))
    return {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "available_modes": [
            {"key": item, "label": MODE_LABELS[item]} for item in MODES
        ],
        "modules": modules,
        "note": "画像模式只改变展示和推荐软排序，不改变事实画像、证据或岗位匹配分。",
    }


@router.put("/profiles/{user_id}/view-preferences")
async def put_view_preferences(
    user_id: str,
    payload: ViewPreferences,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    await check_write_scope(session, user_id)
    mode = normalise_mode(payload.mode)
    modules = default_modules()
    for key, value in payload.modules.items():
        if key in modules and isinstance(value, bool):
            modules[key] = value
    for kind, value in (
        ("profile_mode", mode),
        ("profile_modules", json.dumps(modules, ensure_ascii=False)),
    ):
        existing = (
            await session.scalars(
                select(UserConstraint).where(
                    UserConstraint.user_id == user_id, UserConstraint.kind == kind
                )
            )
        ).first()
        if existing is None:
            existing = UserConstraint(user_id=user_id, kind=kind, value=value)
            session.add(existing)
        existing.value = value
    await session.commit()
    return {"mode": mode, "mode_label": MODE_LABELS[mode], "modules": modules}


@router.get("/profiles/{user_id}/interview-stories")
async def list_interview_stories(
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(ProfileExtension).where(
            ProfileExtension.user_id == user_id,
            ProfileExtension.dimension_key.like("story:%"),
        ).order_by(ProfileExtension.updated_at.desc())
    )
    return {
        "stories": [{
            "id": row.id,
            "key": row.dimension_key,
            **row.value_json,
            "evidence_ids": row.evidence_ids,
        } for row in rows],
        "note": "每条故事必须锚定真实 Evidence；未核对的表述请标为待补，不要当事实讲述。",
    }


@router.post("/profiles/{user_id}/interview-stories")
async def create_interview_story(
    user_id: str,
    payload: InterviewStory,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    await check_write_scope(session, user_id)
    if payload.evidence_ids:
        found = set(await session.scalars(
            select(Evidence.id).where(
                Evidence.user_id == user_id, Evidence.id.in_(payload.evidence_ids)
            )
        ))
        if not set(payload.evidence_ids) <= found:
            raise HTTPException(
                status_code=422, detail="故事只能引用你自己的 Evidence"
            )
    story_id = str(uuid4())
    record = ProfileExtension(
        id=story_id,
        user_id=user_id,
        dimension_key=f"story:{story_id}",
        value_json={
            "title": payload.title,
            "situation": payload.situation,
            "action": payload.action,
            "result": payload.result,
            "status": "证据支持" if payload.evidence_ids else "待补证据",
        },
        evidence_ids=list(payload.evidence_ids),
        source="self_report",
        enabled=True,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return {"id": record.id, "key": record.dimension_key, "status": record.value_json["status"]}


@router.delete("/profiles/{user_id}/interview-stories/{story_id}")
async def delete_interview_story(
    user_id: str,
    story_id: str,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    record = await session.get(ProfileExtension, story_id)
    if record is None or record.user_id != user_id or not record.dimension_key.startswith("story:"):
        raise HTTPException(status_code=404, detail="Story not found")
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="write"
    )
    await check_write_scope(session, user_id)
    await session.delete(record)
    await session.commit()
    return {"deleted": True, "id": story_id}
