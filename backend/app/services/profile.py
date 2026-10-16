from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.profile.llm_extractor import extract_profile_with_fallback


async def rebuild_profile(session: AsyncSession, user_id: str) -> list[ProfileItem]:
    evidence_result = await session.scalars(
        select(Evidence).where(Evidence.user_id == user_id).order_by(Evidence.created_at)
    )
    evidence = list(evidence_result)
    if not evidence:
        raise ValueError("Import evidence before rebuilding the profile")

    extracted = await extract_profile_with_fallback(evidence)
    confirmed_result = await session.scalars(
        select(ProfileItem).where(ProfileItem.user_id == user_id)
    )
    confirmed = [
        {
            "category": item.category,
            "name": item.name,
            "level": item.level,
            "confidence": item.confidence,
            "evidence_ids": item.evidence_ids,
            "details": item.details,
        }
        for item in confirmed_result
        if item.details.get("source") == "confirmed_user_update"
    ]
    by_key = {(item["category"], item["name"].lower()): item for item in extracted}
    for item in confirmed:
        by_key[(item["category"], item["name"].lower())] = item
    extracted = list(by_key.values())
    await session.execute(delete(ProfileItem).where(ProfileItem.user_id == user_id))
    records = [ProfileItem(user_id=user_id, **item) for item in extracted]
    session.add_all(records)
    await session.commit()
    for record in records:
        await session.refresh(record)
    return records


async def read_profile(session: AsyncSession, user_id: str) -> list[ProfileItem]:
    result = await session.scalars(
        select(ProfileItem)
        .where(ProfileItem.user_id == user_id)
        .order_by(ProfileItem.category, ProfileItem.confidence.desc(), ProfileItem.name)
    )
    return list(result)
