import re
from collections import defaultdict

from app.models.evidence import Evidence
from app.profile.catalog import ROLE_ALIASES, SKILL_ALIASES


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", lowered)
        for alias in aliases
    )


def extract_profile_items(evidence: list[Evidence]) -> list[dict]:
    findings: dict[tuple[str, str], dict] = {}
    mentions: defaultdict[tuple[str, str], int] = defaultdict(int)

    catalogs = (("skill", SKILL_ALIASES), ("target_role", ROLE_ALIASES))
    for record in evidence:
        for category, catalog in catalogs:
            for name, aliases in catalog.items():
                if not _contains_alias(record.content, aliases):
                    continue
                key = (category, name)
                mentions[key] += 1
                item = findings.setdefault(
                    key,
                    {
                        "category": category,
                        "name": name,
                        "evidence_ids": [],
                        "details": {"extractor": "catalog-v1"},
                    },
                )
                if record.id not in item["evidence_ids"]:
                    item["evidence_ids"].append(record.id)

    for key, item in findings.items():
        count = mentions[key]
        source_count = len(item["evidence_ids"])
        item["level"] = min(5, 1 + source_count)
        item["confidence"] = round(min(0.98, 0.55 + 0.1 * count + 0.05 * source_count), 2)
        item["details"]["mention_count"] = count

    return sorted(
        findings.values(), key=lambda item: (item["category"], -item["confidence"], item["name"])
    )
