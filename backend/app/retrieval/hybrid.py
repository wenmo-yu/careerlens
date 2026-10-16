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

    scored: list[tuple[float, Evidence]] = []
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
        exact_bonus = 0.25 if query.lower() in content.lower() else 0.0
        score = 0.45 * dense_score + 0.55 * sparse_score + exact_bonus
        if score > 0:
            scored.append((score, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "evidence_id": _field(record, "id"),
            "score": round(score, 4),
            "source_type": _field(record, "source_type"),
            "source_name": _field(record, "source_name"),
            "content": content,
        }
        for score, record in scored[:limit]
    ]
