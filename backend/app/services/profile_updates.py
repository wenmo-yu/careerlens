import json
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_llm_provider
from app.models.profile import ProfileItem
from app.models.profile_update import ProfileUpdateProposal
from app.services.evidence import create_evidence_chunks


class ProposedChange(BaseModel):
    action: str = Field(pattern="^(upsert|remove)$")
    category: str = Field(pattern="^(skill|experience|interest|target_role|preference)$")
    name: str = Field(min_length=1, max_length=255)
    level: int = Field(default=1, ge=1, le=5)
    confidence: float = Field(default=0.9, ge=0, le=1)


class ProposedChanges(BaseModel):
    changes: list[ProposedChange] = Field(default_factory=list, max_length=10)


def _deterministic_changes(message: str) -> list[dict]:
    changes: list[dict] = []
    remove_match = re.search(
        r"(?:不想|不再|取消|移除|删除)(?:做|从事|考虑)?\s*([^，。；;]+)", message
    )
    if remove_match:
        changes.append(
            {
                "action": "remove",
                "category": "target_role",
                "name": remove_match.group(1).strip(),
                "level": 1,
                "confidence": 1.0,
            }
        )
    target_match = re.search(
        r"(?:更希望|想做|目标是|转向)(?:做|从事)?\s*([^，。；;]+)", message
    )
    if target_match:
        changes.append(
            {
                "action": "upsert",
                "category": "target_role",
                "name": target_match.group(1).strip(),
                "level": 3,
                "confidence": 0.95,
            }
        )
    if not changes:
        changes.append(
            {
                "action": "upsert",
                "category": "preference",
                "name": message.strip()[:255],
                "level": 1,
                "confidence": 0.9,
            }
        )
    return changes


async def create_proposal(
    session: AsyncSession, *, user_id: str, message: str
) -> ProfileUpdateProposal:
    provider = get_llm_provider()
    changes = _deterministic_changes(message)
    if provider.diagnostics["provider"] != "demo":
        try:
            raw = await provider.generate_json(
                system_prompt=(
                    "把用户对长期职业画像的纠正转成最少量变更。不要执行，只输出待确认的变更。"
                    "目标岗位用 target_role，偏好用 preference。"
                ),
                user_prompt=json.dumps({"message": message}, ensure_ascii=False),
                schema=ProposedChanges.model_json_schema(),
                operation="profile_update_proposal",
            )
            parsed = ProposedChanges.model_validate(raw)
            if parsed.changes:
                changes = [item.model_dump() for item in parsed.changes]
        except Exception:
            pass
    proposal = ProfileUpdateProposal(user_id=user_id, message=message, changes=changes)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return proposal


async def list_proposals(
    session: AsyncSession, *, user_id: str, status: str | None = None
) -> list[ProfileUpdateProposal]:
    query = select(ProfileUpdateProposal).where(ProfileUpdateProposal.user_id == user_id)
    if status:
        query = query.where(ProfileUpdateProposal.status == status)
    result = await session.scalars(query.order_by(ProfileUpdateProposal.created_at.desc()))
    return list(result)


async def decide_proposal(
    session: AsyncSession, *, proposal_id: str, approve: bool
) -> ProfileUpdateProposal:
    proposal = await session.get(ProfileUpdateProposal, proposal_id)
    if proposal is None:
        raise LookupError("Profile update proposal not found")
    if proposal.status != "pending":
        raise ValueError("This proposal has already been resolved")
    if approve:
        evidence = await create_evidence_chunks(
            session,
            user_id=proposal.user_id,
            source_type="user_correction",
            source_name="confirmed-profile-update",
            content=proposal.message,
            metadata={"proposal_id": proposal.id},
        )
        evidence_ids = [item.id for item in evidence]
        for change in proposal.changes:
            query = delete(ProfileItem).where(
                ProfileItem.user_id == proposal.user_id,
                ProfileItem.category == change["category"],
                ProfileItem.name == change["name"],
            )
            if change["action"] == "remove":
                await session.execute(query)
                continue
            existing = await session.scalar(
                select(ProfileItem).where(
                    ProfileItem.user_id == proposal.user_id,
                    ProfileItem.category == change["category"],
                    ProfileItem.name == change["name"],
                )
            )
            if existing:
                existing.level = change["level"]
                existing.confidence = change["confidence"]
                existing.evidence_ids = list(dict.fromkeys(existing.evidence_ids + evidence_ids))
                existing.details = {**existing.details, "source": "confirmed_user_update"}
            else:
                session.add(
                    ProfileItem(
                        user_id=proposal.user_id,
                        category=change["category"],
                        name=change["name"],
                        level=change["level"],
                        confidence=change["confidence"],
                        evidence_ids=evidence_ids,
                        details={"source": "confirmed_user_update"},
                    )
                )
        proposal.status = "approved"
    else:
        proposal.status = "rejected"
    proposal.resolved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(proposal)
    return proposal
