"""Validate model-authored Evidence references before showing them to users."""

import re

_INLINE_CITATION = re.compile(r"\[Evidence:\s*([^\]\n]+)\]")


def validated_citations(
    texts: list[str], requested_ids: list[str], allowed_ids: set[str]
) -> list[str]:
    """Return allowed IDs in first-seen order, rejecting fabricated inline references."""
    inline_ids = [
        match.group(1).strip() for value in texts for match in _INLINE_CITATION.finditer(value)
    ]
    if any(evidence_id not in allowed_ids for evidence_id in inline_ids):
        raise ValueError("Model answer contains an unknown Evidence citation")
    return list(
        dict.fromkeys(
            evidence_id
            for evidence_id in [*inline_ids, *requested_ids]
            if evidence_id in allowed_ids
        )
    )
