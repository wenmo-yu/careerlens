"""HY4-C: local, versioned role/course catalogs.

The catalogs are teaching templates shipped with the repository. They are
never fetched at runtime and never used to assert market facts. Loading them
validates structure so a broken edit fails loudly instead of silently
producing empty recommendations.
"""

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

_CATALOG_DIR = Path(__file__).resolve().parent
_ALLOWED_SCHEMES = {"http", "https"}
_ROLE_KEYS = {
    "role_id", "name", "family", "typical_tasks", "required_skills",
    "nice_to_have", "entry_evidence", "growth_path", "source_note", "riasec",
}
_COURSE_KEYS = {
    "course_id", "title", "skill", "level", "format", "provider",
    "estimated_hours", "cost", "prerequisites", "url", "license",
    "language", "last_checked_at", "alternative_ids", "verification",
}


def _load(filename: str) -> list[dict]:
    path = _CATALOG_DIR / filename
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, list) or not data:
        raise ValueError(f"{filename} must be a non-empty JSON array")
    return data


@lru_cache(maxsize=1)
def load_roles() -> tuple[dict, ...]:
    rows = _load("roles.json")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        missing = _ROLE_KEYS - set(row)
        if missing:
            raise ValueError(f"roles.json[{index}] missing fields: {sorted(missing)}")
        if row["role_id"] in seen:
            raise ValueError(f"roles.json duplicate role_id: {row['role_id']}")
        seen.add(row["role_id"])
        list_keys = (
            "typical_tasks", "required_skills", "nice_to_have",
            "entry_evidence", "growth_path",
        )
        for key in list_keys:
            if not isinstance(row[key], list) or not all(
                isinstance(item, str) for item in row[key]
            ):
                raise ValueError(f"roles.json[{index}].{key} must be a string list")
        if "本地教学模板" not in row["source_note"]:
            raise ValueError(
                f"roles.json[{index}] must declare source_note as a local teaching template"
            )
        letters = row["riasec"]
        if (
            not isinstance(letters, list)
            or not 1 <= len(letters) <= 3
            or len(set(letters)) != len(letters)
            or any(letter not in "RIASEC" for letter in letters)
        ):
            raise ValueError(
                f"roles.json[{index}].riasec must be 1-3 unique letters from RIASEC"
            )
    return tuple(rows)


@lru_cache(maxsize=1)
def load_courses() -> tuple[dict, ...]:
    rows = _load("courses.json")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        missing = _COURSE_KEYS - set(row)
        if missing:
            raise ValueError(f"courses.json[{index}] missing fields: {sorted(missing)}")
        if row["course_id"] in seen:
            raise ValueError(f"courses.json duplicate course_id: {row['course_id']}")
        seen.add(row["course_id"])
        parsed = urlparse(row["url"])
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
            raise ValueError(f"courses.json[{index}].url must be an absolute http(s) URL")
        if not isinstance(row["prerequisites"], list):
            raise ValueError(f"courses.json[{index}].prerequisites must be a list")
        if not isinstance(row["estimated_hours"], (int, float)) or row["estimated_hours"] <= 0:
            raise ValueError(f"courses.json[{index}].estimated_hours must be positive")
        try:
            year, month, day = (int(part) for part in row["last_checked_at"].split("-"))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"courses.json[{index}].last_checked_at must be YYYY-MM-DD") from exc
        if year < 2020 or month < 1 or month > 12 or day < 1 or day > 31:
            raise ValueError(f"courses.json[{index}].last_checked_at is invalid")
    known = {row["course_id"] for row in rows}
    for row in rows:
        for prerequisite in row["prerequisites"]:
            if prerequisite not in known:
                raise ValueError(
                    f"courses.json[{row['course_id']}] has unknown prerequisite {prerequisite}"
                )
        for alternative in row["alternative_ids"]:
            if alternative not in known:
                raise ValueError(
                    f"courses.json[{row['course_id']}] has unknown alternative {alternative}"
                )
    return tuple(rows)


def clear_cache() -> None:
    """For tests that write temporary catalog files."""
    load_roles.cache_clear()
    load_courses.cache_clear()
