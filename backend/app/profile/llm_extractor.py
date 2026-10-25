import json

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.models.evidence import Evidence
from app.profile.extractor import extract_profile_items


class ExtractedItem(BaseModel):
    category: str = Field(pattern="^(skill|experience|interest|target_role|preference)$")
    name: str = Field(min_length=1, max_length=255)
    level: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    details: dict = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list)


def _merge_items(deterministic: list[dict], generated: list[dict]) -> list[dict]:
    merged = {(item["category"], item["name"].lower()): item for item in deterministic}
    for item in generated:
        key = (item["category"], item["name"].lower())
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        current["level"] = max(current["level"], item["level"])
        current["confidence"] = max(current["confidence"], item["confidence"])
        current["evidence_ids"] = list(
            dict.fromkeys(current["evidence_ids"] + item["evidence_ids"])
        )
        current["details"] = {**current["details"], **item["details"]}
    return sorted(
        merged.values(), key=lambda item: (item["category"], -item["confidence"], item["name"])
    )


async def extract_profile_with_fallback(
    evidence: list[Evidence], provider: LLMProvider | None = None
) -> list[dict]:
    deterministic = extract_profile_items(evidence)
    model = provider or get_llm_provider()
    if model.diagnostics["provider"] == "demo":
        return deterministic
    allowed_ids = {record.id for record in evidence}
    preference_ids = {
        record.id
        for record in evidence
        if record.source_metadata.get("claim_strength") == "preference_signal"
    }
    source = [
        {"evidence_id": record.id, "source": record.source_name, "content": record.content}
        for record in evidence
    ]
    try:
        raw = await model.generate_json(
            system_prompt=(
                "你是职业画像抽取器。只提取证据直接支持的事实；每个条目必须引用输入中的"
                " evidence_id，不得推测人格、能力或经历。点赞、收藏和关注仅是兴趣线索，"
                "不能据此声称用户掌握技能、拥有经历或目标岗位。"
            ),
            user_prompt=json.dumps(source, ensure_ascii=False),
            schema=ExtractionResult.model_json_schema(),
            operation="profile_extraction",
        )
        parsed = ExtractionResult.model_validate(raw)
    except Exception:
        return deterministic
    generated = []
    for item in parsed.items:
        valid_ids = list(
            dict.fromkeys(item_id for item_id in item.evidence_ids if item_id in allowed_ids)
        )
        if item.category in {"skill", "experience", "target_role"}:
            valid_ids = [item_id for item_id in valid_ids if item_id not in preference_ids]
        if not valid_ids:
            continue
        data = item.model_dump()
        data["evidence_ids"] = valid_ids
        data["details"] = {**data["details"], "extractor": model.diagnostics}
        generated.append(data)
    return _merge_items(deterministic, generated)
