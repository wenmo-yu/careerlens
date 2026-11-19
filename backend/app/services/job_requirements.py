"""Extract JD requirements with a constrained model path and a reproducible fallback."""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.profile.alias_match import affirmed_alias_matches
from app.profile.catalog import SKILL_ALIASES

_CLAUSE_BREAK = re.compile(r"[，,。；;！？!?\r\n]+|\.(?=\s|$)")
_PREFERRED = re.compile(r"加分|优先|\b(?:preferred|a plus|nice[ -]to[ -]have|optional)\b", re.I)
_REQUIRED = re.compile(r"必需|必须|要求|\b(?:required|requirements|must(?: have)?)\b", re.I)
_PRIORITY_HEADER = re.compile(
    r"(?P<label>必需(?:技能|项)?|必备技能|岗位要求|要求|加分项?|优先"
    r"|required(?: skills)?|requirements|must have|preferred(?: skills)?"
    r"|nice[ -]to[ -]have|optional)\s*[:：]\s*(?P<body>.*)",
    re.I,
)
_NEGATED_CLAUSE = re.compile(
    r"^(?:不要求|无需|无须|不需要|不必|not required\b|no need\b)", re.I
)


class ExtractedRequirement(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    priority: Literal["required", "preferred"]
    quote: str = Field(min_length=2, max_length=200)


class RequirementExtraction(BaseModel):
    requirements: list[ExtractedRequirement] = Field(default_factory=list)


def _mentions(text: str, aliases: tuple[str, ...]) -> bool:
    return any(affirmed_alias_matches(text, aliases))


def normalize_skill(name: str) -> str:
    """Use one catalog spelling for known skills; keep explicit long-tail names."""
    value = " ".join(name.strip().split())
    for canonical, aliases in SKILL_ALIASES.items():
        if value.casefold() in {canonical.casefold(), *(alias.casefold() for alias in aliases)}:
            return canonical
    return value


def extract_requirements(jd_text: str) -> list[dict]:
    requirements: dict[str, str] = {}
    section_priority = "required"
    for raw_clause in _CLAUSE_BREAK.split(jd_text):
        clause = raw_clause.strip().lstrip("-*• ").strip()
        if not clause or _NEGATED_CLAUSE.match(clause):
            continue
        heading = _PRIORITY_HEADER.fullmatch(clause)
        if heading:
            section_priority = "preferred" if _PREFERRED.search(heading["label"]) else "required"
            clause = heading["body"]
            if not clause:
                continue
        preferred = bool(_PREFERRED.search(clause))
        required = bool(_REQUIRED.search(clause))
        priority = "required" if required else "preferred" if preferred else section_priority
        for skill, aliases in SKILL_ALIASES.items():
            if _mentions(clause, aliases) and requirements.get(skill) != "required":
                requirements[skill] = priority
    return [
        {"name": skill, "priority": requirements[skill]}
        for skill in SKILL_ALIASES
        if skill in requirements
    ]


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
    elif not _mentions(quote, (name,)):
        return None
    if _NEGATED_CLAUSE.match(quote):
        return None
    priority = item.priority
    if priority == "preferred" and (not _PREFERRED.search(quote) or _REQUIRED.search(quote)):
        priority = "required"
    return {"name": name, "priority": priority}


async def extract_requirements_with_fallback(
    jd_text: str, provider: LLMProvider | None = None
) -> tuple[list[dict], dict]:
    rules = extract_requirements(jd_text)
    model = provider or get_llm_provider("analysis")
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
    catalog_matches = set(merged)
    accepted = 0
    for item in parsed.requirements:
        valid = _validated_model_requirement(item, jd_text)
        if valid is None:
            continue
        key = valid["name"].casefold()
        if key not in catalog_matches and merged.get(key, {}).get("priority") != "required":
            merged[key] = valid
        accepted += 1
    return list(merged.values()), {
        "method": "model_plus_catalog" if accepted else "catalog_rules",
        "model_used": True,
        "accepted": accepted,
    }
