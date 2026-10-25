"""Conservative alias matching for explicit skills and requirements."""

import re
from collections.abc import Iterator

_CLAUSE_BREAK = re.compile(r"[，。；;！？!?\n]")
_NEGATION_BEFORE = re.compile(r"(?:不要求|无需|无须|不需要|尚未掌握|未掌握|不会|未使用|未接触)\s*$")


def affirmed_alias_matches(text: str, aliases: tuple[str, ...]) -> Iterator[re.Match[str]]:
    """Skip clear negated mentions; ambiguous phrasing still needs human review."""
    lowered = text.casefold()
    for alias in aliases:
        pattern = rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])"
        for match in re.finditer(pattern, lowered):
            before = lowered[: match.start()]
            breaks = list(_CLAUSE_BREAK.finditer(before))
            clause_before = before[breaks[-1].end() :] if breaks else before
            if _NEGATION_BEFORE.search(clause_before):
                continue
            yield match
