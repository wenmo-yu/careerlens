from typing import Any

from app.models.evidence import Evidence
from app.profile.catalog import ROLE_ALIASES, SKILL_ALIASES
from app.profile.extractor import extract_profile_items
from app.retrieval.hybrid import hybrid_search
from app.schemas.evaluation import EvaluationDataset
from app.services.jobs import extract_requirements


def _f1(predicted: set[Any], expected: set[Any]) -> tuple[float, float, float]:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _is_supported(item: dict, evidence_by_id: dict[str, Evidence]) -> bool:
    aliases = SKILL_ALIASES.get(item["name"], ()) or ROLE_ALIASES.get(item["name"], ())
    if not aliases or not item["evidence_ids"]:
        return False
    for evidence_id in item["evidence_ids"]:
        record = evidence_by_id.get(evidence_id)
        if record and any(alias.lower() in record.content.lower() for alias in aliases):
            return True
    return False


def run_evaluation(dataset: EvaluationDataset) -> tuple[dict, dict]:
    profile_predicted: set[tuple[str, str]] = set()
    profile_expected: set[tuple[str, str]] = set()
    requirement_predicted: set[tuple[str, str]] = set()
    requirement_expected: set[tuple[str, str]] = set()
    retrieval_scores: list[float] = []
    supported_claims = 0
    claim_count = 0
    case_details = []

    for case in dataset.cases:
        records = [
            Evidence(
                id=item.id,
                user_id=f"eval:{case.id}",
                source_type=item.source_type,
                source_name=item.source_name,
                content=item.content,
                chunk_index=0,
                source_metadata={"evaluation": True},
            )
            for item in case.evidence
        ]
        evidence_by_id = {item.id: item for item in records}
        extracted = extract_profile_items(records)
        case_profile = {(item["category"], item["name"]) for item in extracted}
        expected_profile = {(item.category, item.name) for item in case.expected_profile}
        profile_predicted.update((case.id, *item) for item in case_profile)
        profile_expected.update((case.id, *item) for item in expected_profile)

        for item in extracted:
            claim_count += 1
            supported_claims += int(_is_supported(item, evidence_by_id))

        for query in case.retrieval_queries:
            results = hybrid_search(query.query, records, limit=dataset.recall_k)
            retrieved = {item["evidence_id"] for item in results}
            relevant = set(query.relevant_evidence_ids)
            retrieval_scores.append(len(retrieved & relevant) / len(relevant))

        requirements = extract_requirements(case.jd_text) if case.jd_text else []
        profile_by_name = {item["name"]: item for item in extracted}
        predicted_labels = set()
        for requirement in requirements:
            profile_item = profile_by_name.get(requirement["name"])
            status = (
                "gap"
                if profile_item is None
                else "strong"
                if profile_item["level"] >= 3
                else "partial"
            )
            predicted_labels.add((requirement["name"], status))
        expected_labels = {(item.name, item.status) for item in case.expected_requirements}
        requirement_predicted.update((case.id, *item) for item in predicted_labels)
        requirement_expected.update((case.id, *item) for item in expected_labels)
        case_details.append(
            {
                "case_id": case.id,
                "predicted_profile": sorted([list(item) for item in case_profile]),
                "predicted_requirements": sorted([list(item) for item in predicted_labels]),
            }
        )

    profile_precision, profile_recall, profile_f1 = _f1(profile_predicted, profile_expected)
    requirement_precision, requirement_recall, requirement_f1 = _f1(
        requirement_predicted, requirement_expected
    )
    metrics = {
        "profile_extraction_f1": round(profile_f1, 4),
        "evidence_recall_at_k": round(
            sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0.0, 4
        ),
        "supported_claim_rate": round(supported_claims / claim_count if claim_count else 0.0, 4),
        "requirement_matching_f1": round(requirement_f1, 4),
        "profile_precision": round(profile_precision, 4),
        "profile_recall": round(profile_recall, 4),
        "requirement_precision": round(requirement_precision, 4),
        "requirement_recall": round(requirement_recall, 4),
        "case_count": len(dataset.cases),
        "query_count": len(retrieval_scores),
        "claim_count": claim_count,
        "recall_k": dataset.recall_k,
    }
    return metrics, {"cases": case_details}
