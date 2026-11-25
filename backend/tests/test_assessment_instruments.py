"""Assessment packs: licence metadata, deterministic scoring and API contracts."""

import json
from pathlib import Path

import pytest

from app.assessment import ScoringError, get_instrument, list_instruments, score_answers
from app.assessment.loader import _validate
from app.catalog.loader import load_roles


def _answers(instrument_id: str, value_for) -> dict[str, int]:
    instrument = get_instrument(instrument_id)
    assert instrument is not None
    return {item["id"]: value_for(item) for item in instrument["items"]}


def test_packs_declare_licence_and_limits():
    rows = list_instruments()
    assert {row["instrument_id"] for row in rows} == {
        "work_style_4d", "riasec_interest", "big_five_20"
    }
    for row in rows:
        instrument = get_instrument(row["instrument_id"])
        assert instrument is not None
        assert instrument["license"]["items"] == "project-authored"
        assert instrument["license"]["not_used"]
        assert "未做" in instrument["disclaimer"]
        assert all("MBTI" not in item["text"] for item in instrument["items"])


def test_dichotomy_scoring_is_deterministic_and_flags_balance():
    answers = _answers(
        "work_style_4d",
        lambda item: 4 if item.get("pole") in {"I", "N", "T", "J"} else 2,
    )
    first = score_answers("work_style_4d", answers)
    second = score_answers("work_style_4d", answers)
    assert first["code"] == "INTJ"
    assert first["scores"] == second["scores"]
    assert first["balanced_dimensions"] == []
    assert first["completeness"] == 1.0
    assert first["license"]["items"] == "project-authored"

    neutral = score_answers(
        "work_style_4d", {item_id: 3 for item_id in answers}
    )
    assert neutral["code"] == "????"
    assert len(neutral["balanced_dimensions"]) == 4
    assert neutral["clarity"] == 0.0


def test_answers_are_validated():
    instrument = get_instrument("work_style_4d")
    assert instrument is not None
    ids = [item["id"] for item in instrument["items"]]
    with pytest.raises(ScoringError, match="Unknown question id"):
        score_answers("work_style_4d", {"nope": 3})
    with pytest.raises(ScoringError, match="至少需要回答"):
        score_answers("work_style_4d", {ids[0]: 3})
    with pytest.raises(ScoringError, match="between 1 and 5"):
        score_answers("work_style_4d", {item_id: 9 for item_id in ids})
    with pytest.raises(ScoringError, match="integers"):
        score_answers("work_style_4d", {item_id: "3" for item_id in ids})  # type: ignore[dict-item]
    with pytest.raises(ScoringError, match="Unknown assessment instrument"):
        score_answers("missing-pack", {})


def test_partial_answers_are_allowed_above_threshold():
    instrument = get_instrument("riasec_interest")
    assert instrument is not None
    answers: dict[str, int] = {}
    for dimension in instrument["dimensions"]:
        ids = [
            item["id"] for item in instrument["items"]
            if item["dimension"] == dimension["key"]
        ]
        answers.update({item_id: 4 for item_id in ids[:7]})
    result = score_answers("riasec_interest", answers)
    assert result["answered_count"] == 42
    assert 0.8 <= result["completeness"] < 1.0


def test_interest_code_consistency_and_role_hints():
    answers = _answers(
        "riasec_interest", lambda item: 5 if item["dimension"] == "I" else 2
    )
    result = score_answers("riasec_interest", answers)
    assert result["code"][0] == "I"
    assert result["differentiation"] > 0
    roles = {role["role_id"] for role in load_roles()}
    assert all(hint["role_id"] in roles for hint in result["role_hints"])
    assert all("不是能力结论" in hint["reason"] for hint in result["role_hints"])
    assert len(result["hints"]) == 2


def test_trait_scoring_applies_reverse_keys():
    answers = _answers("big_five_20", lambda item: 4)
    result = score_answers("big_five_20", answers)
    by_key = {row["key"]: row for row in result["scores"]}
    # O has one reverse item: 4,4,4 -> 2 => mean 3.5 => 62.5
    assert by_key["O"]["score"] == 62.5
    assert by_key["O"]["band"] == "偏高"
    assert by_key["E"]["score"] == 50.0
    assert result["hints"]


def test_interest_adjacent_dimensions_wrap_around_the_hexagon():
    scores = {"C": 5, "R": 4, "I": 3}
    answers = _answers("riasec_interest", lambda item: scores.get(item["dimension"], 1))
    result = score_answers("riasec_interest", answers)

    assert result["code"] == "CRI"
    assert result["consistency"]["level"] == "高"
    assert result["consistency"]["adjacent_pairs"] == 2


def test_tutorial_assessment_fixtures_are_complete():
    fixture_root = Path(__file__).resolve().parents[2] / "examples/tutorials/fixtures"
    pack = fixture_root / "my_scale.json"
    sample = _validate(json.loads(pack.read_text(encoding="utf-8")), pack.name)
    answers = json.loads((fixture_root / "work-style-neutral.json").read_text(encoding="utf-8"))

    assert len(sample["dimensions"]) == 2
    assert len(sample["items"]) == 6
    assert answers["consent"] is True
    result = score_answers("work_style_4d", answers["answers"])
    assert result["answered_count"] == 32
    assert result["code"] == "????"


async def test_instrument_api_hides_scoring_keys(client):
    listing = await client.get("/api/v1/assessments/instruments")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["instruments"][0]["item_count"] > 0
    assert "未复制" in payload["note"]

    detail = await client.get("/api/v1/assessments/instruments/work_style_4d")
    assert detail.status_code == 200
    body = detail.json()
    assert body["item_count"] == 32
    assert all("reverse" not in item and "pole" not in item for item in body["items"])
    assert body["license"]["not_used"]

    missing = await client.get("/api/v1/assessments/instruments/nope")
    assert missing.status_code == 404


async def test_instrument_submit_stores_result_and_feeds_overview(client):
    user_id = "pack-user"
    answers = _answers(
        "work_style_4d",
        lambda item: 4 if item.get("pole") in {"E", "S", "F", "P"} else 2,
    )
    no_consent = await client.post(
        "/api/v1/assessments/instruments/work_style_4d/submit",
        json={"user_id": user_id, "answers": answers, "consent": False},
    )
    assert no_consent.status_code == 422

    submitted = await client.post(
        "/api/v1/assessments/instruments/work_style_4d/submit",
        json={"user_id": user_id, "answers": answers, "consent": True},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["result"]["code"] == "ESFP"
    assert body["version"] == "2026.11"
    assert "不是能力事实" in body["note"]

    overview = await client.get(f"/api/v1/profiles/{user_id}/overview")
    assert overview.status_code == 200
    highlights = overview.json()["assessments"]
    assert highlights[0]["instrument"] == "work_style_4d"
    assert highlights[0]["code"] == "ESFP"
    assert highlights[0]["title"] == "四维工作偏好（探索版）"


async def test_instrument_submit_rejects_incomplete_answers(client):
    response = await client.post(
        "/api/v1/assessments/instruments/riasec_interest/submit",
        json={"user_id": "pack-partial", "answers": {}, "consent": True},
    )
    assert response.status_code == 422
    assert "至少需要回答" in response.json()["detail"]


async def test_rapid_retake_keeps_both_results(client):
    """Two submissions in the same second must not collide on taken_at."""
    user_id = "pack-rapid"
    instrument = get_instrument("work_style_4d")
    assert instrument is not None
    answers = {item["id"]: 3 for item in instrument["items"]}
    first = await client.post(
        "/api/v1/assessments/instruments/work_style_4d/submit",
        json={"user_id": user_id, "answers": answers, "consent": True},
    )
    second = await client.post(
        "/api/v1/assessments/instruments/work_style_4d/submit",
        json={"user_id": user_id, "answers": answers, "consent": True},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]
