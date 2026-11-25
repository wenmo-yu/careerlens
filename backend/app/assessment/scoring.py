"""Deterministic scoring for the local assessment packs.

No norms, no percentile claims. A score is a within-person position on the
instrument's own response scale, and every result says so. The same answers
always produce the same result, which is what makes the tests cheap.
"""

from math import ceil

from app.assessment.loader import get_instrument
from app.catalog.loader import load_roles

_HEX_ORDER = {"R": 0, "I": 1, "A": 2, "S": 3, "E": 4, "C": 5}
_BALANCED_THRESHOLD = 10.0


class ScoringError(ValueError):
    """Raised for unknown instruments, unknown items or incomplete answers."""


def _mean(values: list[int]) -> float:
    return sum(values) / len(values)


def _position(value: float, low: int, high: int) -> float:
    return round((value - low) / (high - low) * 100, 1)


def _clean_answers(instrument: dict, answers: dict[str, int]) -> dict[str, int]:
    scale = instrument["response_scale"]
    low, high = scale["min"], scale["max"]
    items = {item["id"]: item for item in instrument["items"]}
    unknown = sorted(set(answers) - set(items))
    if unknown:
        raise ScoringError(f"Unknown question id: {unknown[0]}")
    cleaned: dict[str, int] = {}
    for key, value in answers.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ScoringError("Answers must be integers")
        if not low <= value <= high:
            raise ScoringError(f"Answers must be between {low} and {high}")
        cleaned[key] = value

    total = len(items)
    minimum = ceil(total * 0.8)
    if len(cleaned) < minimum:
        raise ScoringError(f"至少需要回答 {minimum}/{total} 题，当前 {len(cleaned)} 题")

    for dimension in instrument["dimensions"]:
        ids = [
            item["id"] for item in instrument["items"]
            if item["dimension"] == dimension["key"]
        ]
        answered = [item_id for item_id in ids if item_id in cleaned]
        required = max(2, ceil(len(ids) * 0.5))
        if len(answered) < required:
            raise ScoringError(
                f"维度「{dimension['label']}」至少需要回答 {required} 题，当前 {len(answered)} 题"
            )
        if instrument["scoring"]["type"] == "dichotomy":
            for pole in dimension["poles"]:
                pole_ids = [
                    item["id"] for item in instrument["items"]
                    if item["dimension"] == dimension["key"]
                    and item["pole"] == pole["key"]
                ]
                pole_answered = [item_id for item_id in pole_ids if item_id in cleaned]
                if len(pole_answered) < 2:
                    raise ScoringError(
                        f"维度「{dimension['label']}」的两个方向都需要至少回答 2 题"
                    )
    return cleaned


def _keyed(item: dict, value: int, low: int, high: int) -> int:
    return (low + high) - value if item.get("reverse") else value


def _score_dichotomy(instrument: dict, answers: dict[str, int]) -> dict:
    low, high = instrument["response_scale"]["min"], instrument["response_scale"]["max"]
    scores = []
    letters = []
    strengths = []
    balanced_dimensions = []
    hints = []
    for dimension in instrument["dimensions"]:
        pole_rows = []
        for pole in dimension["poles"]:
            values = [
                answers[item["id"]]
                for item in instrument["items"]
                if item["dimension"] == dimension["key"]
                and item["pole"] == pole["key"]
                and item["id"] in answers
            ]
            mean = _mean(values)
            pole_rows.append({
                "key": pole["key"],
                "label": pole["label"],
                "mean": round(mean, 2),
                "percent": _position(mean, low, high),
                "answered": len(values),
            })
        left, right = pole_rows
        difference = abs(left["mean"] - right["mean"])
        strength = round(difference / (high - low) * 100, 1)
        if difference < 1e-9:
            letter = "?"
        else:
            letter = left["key"] if left["mean"] > right["mean"] else right["key"]
        balanced = strength < _BALANCED_THRESHOLD
        if balanced:
            balanced_dimensions.append(dimension["key"])
        letters.append(letter)
        strengths.append(strength)
        scores.append({
            "dimension": dimension["key"],
            "label": dimension["label"],
            "letter": letter,
            "strength": strength,
            "balanced": balanced,
            "poles": pole_rows,
        })
        chosen = next(
            (pole for pole in dimension["poles"] if pole["key"] == letter), None
        )
        if chosen is not None:
            hints.append(chosen["hint"])

    code = "".join(letters)
    return {
        "scoring_type": "dichotomy",
        "code": code,
        "code_label": "偏好组合（非 MBTI 官方类型）",
        "scores": scores,
        "clarity": round(_mean(strengths), 1) if strengths else 0.0,
        "balanced_dimensions": balanced_dimensions,
        "hints": hints,
        "methodology": (
            "每个方向取其题目均值，换算为量程内位置；差值小于 10% 视为接近中点，"
            "字母仅表示本次作答的相对高低，不代表固定类型。"
        ),
    }


def _hex_consistency(code: str) -> dict:
    gaps = []
    for first, second in zip(code, code[1:], strict=False):
        if first in _HEX_ORDER and second in _HEX_ORDER:
            gaps.append(abs(_HEX_ORDER[first] - _HEX_ORDER[second]))
    if not gaps:
        level = "无法判断"
    elif max(gaps) <= 1:
        level = "高"
    elif max(gaps) <= 2:
        level = "中"
    else:
        level = "低"
    return {
        "level": level,
        "adjacent_pairs": sum(1 for gap in gaps if gap <= 1),
        "pairs": len(gaps),
        "note": "相邻类型更相似；跨度大表示兴趣分布更分散，适合组合型方向。",
    }


def _role_hints(scores: list[dict], limit: int = 3) -> list[dict]:
    by_key = {row["key"]: row["score"] for row in scores}
    if not by_key:
        return []
    rows = []
    for role in load_roles():
        letters = role.get("riasec") or []
        if not letters:
            continue
        matched = [letter for letter in letters if letter in by_key]
        if not matched:
            continue
        match = round(_mean([by_key[letter] for letter in matched]), 1)
        names = {
            row["key"]: row["label"] for row in scores
        }
        rows.append({
            "role_id": role["role_id"],
            "name": role["name"],
            "family": role["family"],
            "riasec": letters,
            "match": match,
            "reason": (
                "兴趣代码中的 "
                + "、".join(f"{letter}（{names.get(letter, letter)}）" for letter in matched)
                + " 与该方向重合；这是方向线索，不是能力结论。"
            ),
        })
    rows.sort(key=lambda row: (-row["match"], row["role_id"]))
    return rows[:limit]


def _score_interest(instrument: dict, answers: dict[str, int]) -> dict:
    low, high = instrument["response_scale"]["min"], instrument["response_scale"]["max"]
    hints_by_key: dict[str, str] = {}
    scores = []
    for dimension in instrument["dimensions"]:
        values = [
            answers[item["id"]]
            for item in instrument["items"]
            if item["dimension"] == dimension["key"] and item["id"] in answers
        ]
        mean = _mean(values)
        scores.append({
            "key": dimension["key"],
            "label": dimension["label"],
            "description": dimension["description"],
            "mean": round(mean, 2),
            "score": _position(mean, low, high),
            "answered": len(values),
        })
        hints_by_key[dimension["key"]] = dimension["hint"]

    ranked = sorted(scores, key=lambda row: (-row["score"], _HEX_ORDER[row["key"]]))
    code_length = int(instrument["scoring"].get("code_length", 3))
    code = "".join(row["key"] for row in ranked[:code_length])
    top = ranked[0]["score"] if ranked else 0.0
    bottom = ranked[-1]["score"] if ranked else 0.0
    focus_hints = [hints_by_key[row["key"]] for row in ranked[:2]]
    return {
        "scoring_type": "interest",
        "code": code,
        "code_label": "兴趣代码（前三项）",
        "scores": scores,
        "ranked": [row["key"] for row in ranked],
        "consistency": _hex_consistency(code),
        "differentiation": round(top - bottom, 1),
        "hints": focus_hints,
        "role_hints": _role_hints(scores) if instrument["scoring"].get("match_roles") else [],
        "methodology": (
            "六个方向分别取活动意愿均值，换算为量程内位置；取最高三项组成代码。"
            "未做常模换算，分数只表示你在这六类活动之间的相对偏好。"
        ),
    }


def _band(score: float) -> str:
    if score >= 70:
        return "高"
    if score >= 58:
        return "偏高"
    if score > 42:
        return "中"
    if score > 30:
        return "偏低"
    return "低"


def _score_trait(instrument: dict, answers: dict[str, int]) -> dict:
    low, high = instrument["response_scale"]["min"], instrument["response_scale"]["max"]
    scores = []
    hints = []
    for dimension in instrument["dimensions"]:
        values = [
            _keyed(item, answers[item["id"]], low, high)
            for item in instrument["items"]
            if item["dimension"] == dimension["key"] and item["id"] in answers
        ]
        mean = _mean(values)
        score = _position(mean, low, high)
        band = _band(score)
        if score >= 58:
            description = dimension["high"]
        elif score <= 42:
            description = dimension["low"]
        else:
            description = "处于中间区间，会随情境调整；没有明显偏向。"
        scores.append({
            "key": dimension["key"],
            "label": dimension["label"],
            "score": score,
            "band": band,
            "description": description,
        })
        if band in {"高", "偏高", "低", "偏低"}:
            hints.append(description)
    return {
        "scoring_type": "trait",
        "code": None,
        "code_label": None,
        "scores": scores,
        "hints": hints,
        "methodology": (
            "反向题先按量程翻转，再逐因素取均值并换算为量程内位置；"
            "分档只描述本次作答的位置，不是常模百分位。"
        ),
    }


def score_answers(instrument_id: str, answers: dict[str, int]) -> dict:
    instrument = get_instrument(instrument_id)
    if instrument is None:
        raise ScoringError("Unknown assessment instrument")
    cleaned = _clean_answers(instrument, answers)
    if instrument["scoring"]["type"] == "dichotomy":
        result = _score_dichotomy(instrument, cleaned)
    elif instrument["scoring"]["type"] == "interest":
        result = _score_interest(instrument, cleaned)
    else:
        result = _score_trait(instrument, cleaned)

    total = len(instrument["items"])
    result.update({
        "instrument_id": instrument["instrument_id"],
        "instrument_version": instrument["version"],
        "instrument_title": instrument["title"],
        "answered_count": len(cleaned),
        "item_count": total,
        "completeness": round(len(cleaned) / total, 3),
        "license": instrument["license"],
        "disclaimer": instrument["disclaimer"],
    })
    return result


__all__ = ["ScoringError", "score_answers"]
