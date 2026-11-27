import math
import re
from collections import Counter
from typing import Any

from app.models.evidence import Evidence


def tokenize(text: str) -> list[str]:
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9.+#-]*", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    chinese_bigrams = [
        token[index : index + 2] for token in chinese for index in range(len(token) - 1)
    ]
    return latin + chinese + chinese_bigrams


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    numerator = sum(value * right.get(token, 0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _field(record: Evidence | dict[str, Any], name: str) -> Any:
    return record[name] if isinstance(record, dict) else getattr(record, name)


def hybrid_search(
    query: str, evidence: list[Evidence | dict[str, Any]], limit: int = 5
) -> list[dict]:
    query_tokens = Counter(tokenize(query))
    if not query_tokens:
        return []

    scored: dict[str, tuple[float, float, bool, str, Evidence | dict[str, Any]]] = {}
    total = max(len(evidence), 1)
    document_frequency = Counter(
        token for record in evidence for token in set(tokenize(_field(record, "content")))
    )
    for record in evidence:
        content = _field(record, "content")
        document_tokens = Counter(tokenize(content))
        dense_score = _cosine(query_tokens, document_tokens)
        sparse_score = sum(
            min(query_tokens[token], document_tokens[token])
            * math.log(1 + total / (1 + document_frequency[token]))
            for token in query_tokens
        )
        sparse_score = sparse_score / max(sum(query_tokens.values()), 1)
        exact = query.casefold() in content.casefold()
        if dense_score or sparse_score:
            scored[_field(record, "id")] = (dense_score, sparse_score, exact, content, record)

    # Fuse rank positions so unbounded corpus-dependent IDF values do not
    # overwhelm cosine. Literal phrase hits also have a separate rank list.
    fused: Counter[str] = Counter()
    for method in range(3):
        ranked = sorted(
            (record_id for record_id, row in scored.items() if row[method]),
            key=lambda record_id: (-scored[record_id][method], record_id),
        )
        for rank, record_id in enumerate(ranked, start=1):
            fused[record_id] += 1 / (60 + rank)
    top = sorted(fused, key=lambda record_id: (-fused[record_id], record_id))[:limit]
    return [
        {
            "evidence_id": record_id,
            "score": round(fused[record_id], 6),
            "source_type": _field(scored[record_id][4], "source_type"),
            "source_name": _field(scored[record_id][4], "source_name"),
            "content": scored[record_id][3],
        }
        for record_id in top
    ]
