"""Self-reported assessments: the quick form and the versioned item packs.

Work preference comes first; the three long packs are optional. Item text lives
in ``app/assessment/data`` and is project-authored: no official MBTI or O*NET
item is copied, and every pack declares its licence. Results are self-reported
and never enter the fact profile or the match score.

Profile dimensions, constraints and view preferences live in
``profile_extensions.py`` so this module stays focused on assessment results.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import (
    ScoringError,
    get_instrument,
    list_instruments,
    public_instrument,
    score_answers,
)
from app.core.database import get_session
from app.models.assessment import AssessmentResult
from app.schemas.assessment import AssessmentSubmit, InstrumentSubmit
from app.security import authorize_user
from app.services.assessment import delete_assessment_result, record_assessment

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Authorization = Annotated[str | None, Header()]

WORK_PREFERENCE_ITEMS = (
    ("deep_focus", "我喜欢长时间独立钻研一个问题"),
    ("collaboration", "我喜欢和团队频繁讨论并一起推进"),
    ("hands_on", "我喜欢动手搭建并立刻看到结果"),
    ("research", "我喜欢持续阅读资料、比较方案"),
    ("coordination", "我喜欢组织任务、跟进进度"),
)
RIASEC_ITEMS = (
    ("R", "我喜欢动手操作设备或工具"),
    ("I", "我喜欢分析数据和研究问题"),
    ("A", "我喜欢创意表达和写作"),
    ("S", "我喜欢帮助他人解决问题"),
    ("E", "我喜欢说服和推动他人"),
    ("C", "我喜欢按规范整理和核对"),
)
LEGACY_INSTRUMENTS = {"work_preference", "riasec", "mbti_label"}
LEGACY_VERSION = "v1"


def _questions(instrument: str) -> tuple[tuple[str, str], ...]:
    if instrument == "work_preference":
        return WORK_PREFERENCE_ITEMS
    if instrument == "riasec":
        return RIASEC_ITEMS
    return ()


@router.get("/assessments/instruments")
async def get_instruments() -> dict:
    """List the versioned, licence-checked item packs available locally."""
    return {
        "instruments": list_instruments(),
        "note": (
            "题目为本项目自写并固定版本；未复制 MBTI®、OEJTS、O*NET Interest Profiler "
            "等受限制题库。结果只作探索，不进入事实画像或岗位匹配分。"
        ),
    }


@router.get("/assessments/instruments/{instrument_id}")
async def get_instrument_detail(instrument_id: str) -> dict:
    instrument = get_instrument(instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Unknown assessment instrument")
    return public_instrument(instrument)


@router.post("/assessments/instruments/{instrument_id}/submit")
async def submit_instrument(
    instrument_id: str,
    payload: InstrumentSubmit,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    """Score a complete-enough submission and store it as self-report."""
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    instrument = get_instrument(instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Unknown assessment instrument")
    if not payload.consent:
        raise HTTPException(status_code=422, detail="请确认这是自愿填写的自陈信息")
    try:
        result = score_answers(instrument_id, payload.answers)
    except ScoringError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = await record_assessment(
        session,
        user_id=payload.user_id,
        instrument=instrument_id,
        version=instrument["version"],
        result=result,
        answers=payload.answers,
    )
    return {
        "id": record.id,
        "instrument": instrument_id,
        "version": record.version,
        "result": result,
        "taken_at": record.taken_at.isoformat(),
        "note": (
            "自陈探索结果，不是能力事实，不进入岗位匹配分；"
            "可在结果列表里重测或删除。"
        ),
    }


@router.get("/assessments/questions/{instrument}")
async def get_questions(instrument: str) -> dict:
    """Legacy quick-form questions; superseded by the item-pack endpoints."""
    if instrument not in LEGACY_INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Unknown assessment instrument")
    return {
        "instrument": instrument,
        "version": LEGACY_VERSION,
        "questions": [{"id": key, "text": text} for key, text in _questions(instrument)],
        "note": (
            "项目自写的探索题，非官方量表；可跳过，结果只作反思与方向探索，"
            "不写入事实画像、不改变岗位匹配分。"
        ),
    }


@router.post("/assessments/{instrument}/submit")
async def submit_assessment(
    instrument: str,
    payload: AssessmentSubmit,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    await authorize_user(
        session, user_id=payload.user_id, authorization=authorization, required_scope="write"
    )
    if instrument not in LEGACY_INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Unknown assessment instrument")
    if not payload.consent:
        raise HTTPException(status_code=422, detail="请确认这是自愿填写的自陈信息")
    allowed = {key for key, _ in _questions(instrument)}
    answers = {}
    for key, value in payload.answers.items():
        if instrument == "mbti_label":
            allowed.add("label")
        elif key not in allowed:
            raise HTTPException(status_code=422, detail=f"Unknown question id: {key}")
        if not isinstance(value, int) or value < 1 or value > 5:
            raise HTTPException(status_code=422, detail="Answers must be integers from 1 to 5")
        answers[key] = value
    if instrument == "mbti_label":
        if not payload.label or len(payload.label) > 50:
            raise HTTPException(status_code=422, detail="请填写自填标签（不超过 50 字）")
        result = {"label": payload.label}
    elif instrument == "riasec":
        result = {"scores": sorted(
            ((key, value) for key, value in answers.items()), key=lambda item: -item[1]
        )}
    else:
        result = {"top": sorted(answers.items(), key=lambda item: -item[1])[:3]}
    record = await record_assessment(
        session,
        user_id=payload.user_id,
        instrument=instrument,
        version=LEGACY_VERSION,
        result=result,
        answers=answers,
    )
    return {
        "id": record.id, "instrument": instrument, "version": LEGACY_VERSION,
        "result": result, "taken_at": record.taken_at.isoformat(),
        "note": "自陈探索结果，不是能力事实，不进入岗位匹配分。",
    }


@router.get("/assessments/results")
async def list_results(
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> list[dict]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    rows = await session.scalars(
        select(AssessmentResult).where(AssessmentResult.user_id == user_id)
        .order_by(AssessmentResult.taken_at.desc())
    )
    return [{
        "id": row.id, "instrument": row.instrument, "version": row.version,
        "result": row.result_json, "taken_at": row.taken_at.isoformat(),
        "source": row.source,
    } for row in rows]


@router.delete("/assessments/results/{result_id}")
async def delete_result(
    result_id: str,
    user_id: str,
    session: Session,
    authorization: Authorization = None,
) -> dict:
    record = await session.get(AssessmentResult, result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Assessment result not found")
    await authorize_user(
        session, user_id=record.user_id, authorization=authorization, required_scope="write"
    )
    await delete_assessment_result(session, record)
    return {"deleted": True, "id": result_id}
