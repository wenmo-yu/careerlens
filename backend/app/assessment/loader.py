"""Versioned, license-checked assessment item packs.

The packs are local JSON files shipped with the repository. Nothing is fetched
at runtime. Loading validates structure so a broken edit fails loudly instead
of silently producing a wrong score.

Licensing policy
----------------
* Items are project-authored; the packs record what was deliberately *not*
  copied (MBTI®, OEJTS, O*NET Interest Profiler, NEO-PI-3, ...).
* We never call a result an official type. Every pack carries a disclaimer and
  a license block that the API returns verbatim.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_ALLOWED_SCORING = {"dichotomy", "interest", "trait"}
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
_ITEM_ID_PATTERN = re.compile(r"^[a-z]{2}-[a-z0-9]{1,6}-\d{2}$")
_REQUIRED_KEYS = {
    "instrument_id", "version", "title", "subtitle", "construct",
    "estimated_minutes", "response_scale", "license", "disclaimer",
    "scoring", "dimensions", "items",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate(instrument: dict, filename: str) -> dict:
    missing = _REQUIRED_KEYS - set(instrument)
    _require(not missing, f"{filename} missing fields: {sorted(missing)}")
    _require(
        instrument["instrument_id"] == Path(filename).stem,
        f"{filename} instrument_id must equal the file name",
    )
    _require(
        bool(_ID_PATTERN.match(instrument["instrument_id"])),
        f"{filename} instrument_id must be lower_snake_case",
    )
    _require(bool(instrument["version"]), f"{filename} version is required")
    _require(
        isinstance(instrument["estimated_minutes"], int)
        and 1 <= instrument["estimated_minutes"] <= 60,
        f"{filename} estimated_minutes must be 1..60",
    )

    scale = instrument["response_scale"]
    _require(isinstance(scale, dict), f"{filename} response_scale must be an object")
    low, high = scale.get("min"), scale.get("max")
    _require(
        isinstance(low, int) and isinstance(high, int) and 0 < low < high <= 9,
        f"{filename} response_scale min/max are invalid",
    )
    _require(
        isinstance(scale.get("labels"), list)
        and len(scale["labels"]) == high - low + 1
        and all(isinstance(label, str) and label for label in scale["labels"]),
        f"{filename} response_scale labels must match the scale length",
    )
    _require(bool(scale.get("prompt")), f"{filename} response_scale prompt is required")

    scoring = instrument["scoring"]
    _require(
        isinstance(scoring, dict) and scoring.get("type") in _ALLOWED_SCORING,
        f"{filename} scoring.type must be one of {sorted(_ALLOWED_SCORING)}",
    )

    license_block = instrument["license"]
    _require(isinstance(license_block, dict), f"{filename} license must be an object")
    for key in ("items", "license", "attribution", "not_used"):
        _require(bool(license_block.get(key)), f"{filename} license.{key} is required")
    _require(
        isinstance(license_block["not_used"], list) and license_block["not_used"],
        f"{filename} license.not_used must be a non-empty list",
    )
    _require(
        "官方" in instrument["disclaimer"] or "未做" in instrument["disclaimer"],
        f"{filename} disclaimer must state the limits of the result",
    )

    dimensions = instrument["dimensions"]
    _require(isinstance(dimensions, list) and len(dimensions) >= 2, f"{filename} needs dimensions")
    dimension_keys: set[str] = set()
    for dimension in dimensions:
        key = dimension.get("key")
        _require(bool(key) and key not in dimension_keys, f"{filename} duplicate dimension {key}")
        dimension_keys.add(key)
        for field in ("label", "description"):
            _require(bool(dimension.get(field)), f"{filename} dimension {key} missing {field}")
        if scoring["type"] == "dichotomy":
            poles = dimension.get("poles")
            _require(
                isinstance(poles, list) and len(poles) == 2,
                f"{filename} dimension {key} needs exactly two poles",
            )
            pole_keys = {pole.get("key") for pole in poles}
            _require(len(pole_keys) == 2, f"{filename} dimension {key} pole keys must differ")
            for pole in poles:
                _require(
                    bool(pole.get("label")) and bool(pole.get("hint")),
                    f"{filename} dimension {key} pole needs label and hint",
                )
        if scoring["type"] == "interest":
            _require(bool(dimension.get("hint")), f"{filename} dimension {key} needs hint")
        if scoring["type"] == "trait":
            _require(
                bool(dimension.get("high")) and bool(dimension.get("low")),
                f"{filename} dimension {key} needs high/low descriptions",
            )

    items = instrument["items"]
    _require(isinstance(items, list) and items, f"{filename} items are required")
    item_ids: set[str] = set()
    texts: set[str] = set()
    per_dimension: dict[str, int] = {}
    per_pole: dict[tuple[str, str], int] = {}
    for index, item in enumerate(items):
        item_id = item.get("id")
        _require(
            bool(item_id) and bool(_ITEM_ID_PATTERN.match(item_id)),
            f"{filename} items[{index}] has an invalid id",
        )
        _require(item_id not in item_ids, f"{filename} duplicate item id {item_id}")
        item_ids.add(item_id)
        text = (item.get("text") or "").strip()
        _require(2 <= len(text) <= 120, f"{filename} items[{index}].text length is invalid")
        _require(text not in texts, f"{filename} duplicate item text {item_id}")
        texts.add(text)
        dimension_key = item.get("dimension")
        _require(
            dimension_key in dimension_keys,
            f"{filename} items[{index}] references unknown dimension",
        )
        per_dimension[dimension_key] = per_dimension.get(dimension_key, 0) + 1
        reverse = item.get("reverse", False)
        _require(isinstance(reverse, bool), f"{filename} items[{index}].reverse must be boolean")
        if scoring["type"] == "dichotomy":
            pole_key = item.get("pole")
            pole_keys = {
                pole["key"] for pole in next(
                    row for row in dimensions if row["key"] == dimension_key
                )["poles"]
            }
            _require(pole_key in pole_keys, f"{filename} items[{index}] has an unknown pole")
            per_pole[(dimension_key, pole_key)] = per_pole.get(
                (dimension_key, pole_key), 0
            ) + 1
        elif "pole" in item:
            raise ValueError(f"{filename} items[{index}] must not define pole")
        if scoring["type"] != "trait" and reverse:
            raise ValueError(f"{filename} items[{index}] reverse is only valid for traits")

    for dimension in dimensions:
        key = dimension["key"]
        count = per_dimension.get(key, 0)
        _require(count >= 3, f"{filename} dimension {key} needs at least 3 items")
        if scoring["type"] == "dichotomy":
            for pole in dimension["poles"]:
                pole_count = per_pole.get((key, pole["key"]), 0)
                _require(
                    pole_count >= 3,
                    f"{filename} dimension {key} pole {pole['key']} needs at least 3 items",
                )
        if scoring["type"] == "trait":
            reversed_count = sum(
                1 for item in items
                if item["dimension"] == key and item.get("reverse", False)
            )
            _require(
                0 < reversed_count < count,
                f"{filename} dimension {key} needs both keyed and reverse items",
            )

    return instrument


@lru_cache(maxsize=1)
def load_instruments() -> tuple[dict, ...]:
    rows: list[dict] = []
    for path in sorted(_DATA_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        rows.append(_validate(data, path.name))
    if not rows:
        raise ValueError("no assessment instruments found")
    ids = [row["instrument_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate instrument_id in assessment packs")
    return tuple(rows)


def get_instrument(instrument_id: str) -> dict | None:
    for row in load_instruments():
        if row["instrument_id"] == instrument_id:
            return row
    return None


def public_instrument(instrument: dict) -> dict:
    """Return the item text without scoring keys or reverse flags."""
    return {
        "instrument_id": instrument["instrument_id"],
        "version": instrument["version"],
        "title": instrument["title"],
        "subtitle": instrument["subtitle"],
        "construct": instrument["construct"],
        "estimated_minutes": instrument["estimated_minutes"],
        "response_scale": instrument["response_scale"],
        "item_count": len(instrument["items"]),
        "scoring_type": instrument["scoring"]["type"],
        "license": instrument["license"],
        "disclaimer": instrument["disclaimer"],
        "dimensions": [
            {
                "key": dimension["key"],
                "label": dimension["label"],
                "description": dimension["description"],
                **(
                    {"poles": [
                        {"key": pole["key"], "label": pole["label"]}
                        for pole in dimension["poles"]
                    ]}
                    if instrument["scoring"]["type"] == "dichotomy"
                    else {}
                ),
            }
            for dimension in instrument["dimensions"]
        ],
        "items": [
            {
                "id": item["id"],
                "text": item["text"],
                "dimension": item["dimension"],
            }
            for item in instrument["items"]
        ],
    }


def list_instruments() -> list[dict]:
    return [
        {
            "instrument_id": row["instrument_id"],
            "version": row["version"],
            "title": row["title"],
            "subtitle": row["subtitle"],
            "estimated_minutes": row["estimated_minutes"],
            "item_count": len(row["items"]),
            "scoring_type": row["scoring"]["type"],
            "license_summary": f"{row['license']['license']} · {row['license']['items']}",
            "disclaimer": row["disclaimer"],
        }
        for row in load_instruments()
    ]


def clear_cache() -> None:
    """For tests that write temporary packs."""
    load_instruments.cache_clear()
