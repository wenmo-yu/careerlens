"""Regression tests for profile-correction heuristics (phase 1 leftover).

Two historical issues are covered here:

1. "我不再想做 X" matched both the remove and upsert regexes, so approving
   such a correction deleted the item and immediately re-added it.
2. remove used the user's raw wording, which never equalled the catalog key
   the extractor stores, so the item was not actually deleted and rebuilt
   back to life.
"""

from app.services.profile_updates import _canonical_name, _deterministic_changes


def test_canonical_name_maps_alias_to_catalog_key():
    assert _canonical_name("AI Agent 应用开发工作") == "AI Agent 开发"
    assert _canonical_name("大模型应用") == "LLM 应用开发"
    assert _canonical_name("检索增强") == "RAG"
    # Unrecognised wording is preserved verbatim.
    assert _canonical_name("某个全新方向") == "某个全新方向"


def test_no_longer_you_want_emits_only_remove():
    changes = _deterministic_changes("我不再想做 AI Agent 应用开发")
    assert len(changes) == 1
    assert changes[0]["action"] == "remove"
    assert changes[0]["name"] == "AI Agent 开发"


def test_explicit_remove_has_no_upsert():
    changes = _deterministic_changes("移除 LangGraph")
    assert all(change["action"] == "remove" for change in changes)
    assert len(changes) == 1


def test_genuine_change_still_emits_upsert():
    changes = _deterministic_changes("我更希望 AI Agent 应用开发")
    assert len(changes) == 1
    assert changes[0]["action"] == "upsert"
    # Upsert keeps the user's own wording (backward compatible).
    assert changes[0]["name"] == "AI Agent 应用开发"


def test_remove_and_new_target_coexist_when_distinct():
    changes = _deterministic_changes("我不想做 AI Agent 开发了，更希望 RAG 工程师")
    actions = [change["action"] for change in changes]
    assert actions == ["remove", "upsert"]
    assert changes[0]["name"] == "AI Agent 开发"
    assert changes[1]["name"] == "RAG 工程师"
