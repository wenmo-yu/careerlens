"""Extract JD requirements with a constrained model path and a reproducible fallback."""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.profile.catalog import SKILL_ALIASES


class ExtractedRequirement(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    priority: Literal["required", "preferred"]
    quote: str = Field(min_length=2, max_length=200)


class RequirementExtraction(BaseModel):
    requirements: list[ExtractedRequirement] = Field(default_factory=list)


def _mentions(text: str, aliases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", lowered)
        for alias in aliases
    )


def normalize_skill(name: str) -> str:
    """Use one catalog spelling for known skills; keep explicit long-tail names."""
    value = " ".join(name.strip().split())
    for canonical, aliases in SKILL_ALIASES.items():
        if value.casefold() in {canonical.casefold(), *(alias.casefold() for alias in aliases)}:
            return canonical
    return value


def extract_requirements(jd_text: str) -> list[dict]:
    lowered = jd_text.lower()
    requirements: list[dict] = []
    for skill, aliases in SKILL_ALIASES.items():
        match = next(
            (
                found
                for alias in aliases
                if (
                    found := re.search(
                        rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", lowered
                    )
                )
                is not None
            ),
            None,
        )
        if match is None:
            continue
        context = lowered[max(0, match.start() - 20) : match.end() + 20]
        priority = (
            "preferred"
            if any(word in context for word in ("加分", "优先", "preferred", "plus"))
            else "required"
        )
        requirements.append({"name": skill, "priority": priority})
    return requirements


def _validated_model_requirement(item: ExtractedRequirement, jd_text: str) -> dict | None:
    normalized_jd = " ".join(jd_text.split()).casefold()
    quote = " ".join(item.quote.split()).casefold()
    if quote not in normalized_jd:
        return None
    name = normalize_skill(item.name)
    aliases = SKILL_ALIASES.get(name)
    if aliases:
        if not _mentions(quote, aliases):
            return None
    elif name.casefold() not in quote:
        return None
    priority = item.priority
    if priority == "preferred" and not any(
        word in quote for word in ("加分", "优先", "preferred", "plus", "nice to have")
    ):
        priority = "required"
    return {"name": name, "priority": priority}


async def extract_requirements_with_fallback(
    jd_text: str, provider: LLMProvider | None = None
) -> tuple[list[dict], dict]:
    rules = extract_requirements(jd_text)
    model = provider or get_llm_provider()
    if model.diagnostics["provider"] == "demo":
        return rules, {"method": "catalog_rules", "model_used": False, "accepted": 0}

    try:
        raw = await model.generate_json(
            system_prompt=(
                "从岗位描述中提取明确的技术要求。每项提供规范技能名、required/preferred 和"
                "岗位原文中的逐字短引文 quote。不要提取否定要求或推测隐含技能。"
                "没有原文引文的项目不得输出。"
            ),
            user_prompt=json.dumps({"jd_text": jd_text}, ensure_ascii=False),
            schema=RequirementExtraction.model_json_schema(),
            operation="jd_requirement_extraction",
        )
        parsed = RequirementExtraction.model_validate(raw)
    except Exception as exc:
        return rules, {
            "method": "catalog_rules",
            "model_used": True,
            "accepted": 0,
            "fallback_reason": type(exc).__name__,
        }

    merged = {item["name"].casefold(): item for item in rules}
    accepted = 0
    for item in parsed.requirements:
        valid = _validated_model_requirement(item, jd_text)
        if valid is None:
            continue
        merged[valid["name"].casefold()] = valid
        accepted += 1
    return list(merged.values()), {
        "method": "model_plus_catalog" if accepted else "catalog_rules",
        "model_used": True,
        "accepted": accepted,
    }
