from collections import defaultdict

from app.ingestion.claim_strength import is_preference_claim
from app.ingestion.contract import content_fingerprint
from app.models.evidence import Evidence
from app.profile.alias_match import affirmed_alias_matches
from app.profile.catalog import ROLE_ALIASES, SKILL_ALIASES


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    return any(affirmed_alias_matches(text, aliases))


def evidence_source_key(record: Evidence) -> str:
    metadata = record.source_metadata or {}
    document = metadata.get("doc_id") if isinstance(metadata, dict) else None
    return f"document:{document}" if document else content_fingerprint(record.content)


def extract_profile_items(evidence: list[Evidence]) -> list[dict]:
    findings: dict[tuple[str, str], dict] = {}
    mentions: defaultdict[tuple[str, str], int] = defaultdict(int)
    sources: defaultdict[tuple[str, str], set[str]] = defaultdict(set)

    catalogs = (("skill", SKILL_ALIASES), ("target_role", ROLE_ALIASES))
    for record in evidence:
        if is_preference_claim(record.content, record.source_type, record.source_metadata or {}):
            continue
        for category, catalog in catalogs:
            for name, aliases in catalog.items():
                if not _contains_alias(record.content, aliases):
                    continue
                key = (category, name)
                mentions[key] += 1
                sources[key].add(evidence_source_key(record))
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
        source_count = len(sources[key])
        item["level"] = min(5, 1 + source_count)
        item["confidence"] = round(min(0.98, 0.55 + 0.15 * source_count), 2)
        item["details"]["mention_count"] = count
        item["details"]["distinct_source_count"] = source_count
        item["details"]["strength_method"] = "catalog_source_heuristic_v1"

    return sorted(
        findings.values(), key=lambda item: (item["category"], -item["confidence"], item["name"])
    )
