"""Phase 2/D: role-bound models and two-stage cascading rerank."""

import pytest

from app.core.config import get_settings
from app.llm.provider import _get_llm_provider_for, get_llm_provider
from app.retrieval.providers import (
    CascadingReranker,
    LexicalReranker,
    get_reranker_provider,
)


@pytest.fixture(autouse=True)
def reset_config_cache():
    yield
    get_settings.cache_clear()
    _get_llm_provider_for.cache_clear()
    get_reranker_provider.cache_clear()


def test_role_bindings_parse_and_fallback(monkeypatch):
    monkeypatch.setenv(
        "MODEL_ROLE_BINDINGS", "answer=deepseek-chat,wiki=wiki-model, analysis =analysis-model,bad"
    )
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.role_models == {
        "answer": "deepseek-chat",
        "wiki": "wiki-model",
        "analysis": "analysis-model",
    }
    assert settings.model_for_role("wiki") == "wiki-model"
    assert settings.model_for_role("unknown") == settings.ai_model


def test_role_bound_models_are_distinct_instances(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AI_API_KEY", "secret")
    monkeypatch.setenv("AI_MODEL", "default-model")
    monkeypatch.setenv("MODEL_ROLE_BINDINGS", "answer=answer-model,wiki=wiki-model")
    get_settings.cache_clear()
    _get_llm_provider_for.cache_clear()

    answer = get_llm_provider("answer")
    wiki = get_llm_provider("wiki")
    analysis = get_llm_provider("analysis")
    assert answer.model == "answer-model"
    assert wiki.model == "wiki-model"
    assert analysis.model == "default-model"  # no binding -> default
    assert get_llm_provider("answer") is answer  # cached per role
    assert get_llm_provider() is answer  # no-arg defaults to answer role


def test_demo_provider_ignores_role_but_still_resolves(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "demo")
    monkeypatch.setenv("MODEL_ROLE_BINDINGS", "wiki=wiki-model")
    get_settings.cache_clear()
    _get_llm_provider_for.cache_clear()
    assert get_llm_provider("wiki").diagnostics["provider"] == "demo"


def test_cascading_reranker_orders_and_limits_shortlist():
    class FakeCoarse:
        name = "coarse"

        def score(self, query, documents):
            # Score by document length: long docs rank first.
            return [float(len(doc)) for doc in documents]

    class FakeFine:
        name = "fine"

        def __init__(self):
            self.scored = []

        def score(self, query, documents):
            self.scored = list(documents)
            # Reverse: short docs within shortlist get highest fine score.
            return [-float(len(doc)) for doc in documents]

    fine = FakeFine()
    reranker = CascadingReranker(FakeCoarse(), fine, coarse_top_k=3, fine_top_k=2)
    docs = ["a", "bbbb", "ccc", "dd", "eeeeee", "fff"]
    scores = reranker.score("q", docs)
    assert len(scores) == len(docs)
    # Fine pass received only top-3 coarse candidates (by length).
    assert set(fine.scored) == {"eeeeee", "bbbb", "ccc"}
    # Fine pass reorders only its top-2 shortlist (by its own score: shorter
    # ranks higher here), so bbbb outranks eeeeee; ccc never entered fine top-2.
    top2 = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:2]
    assert {docs[i] for i in top2} == {"bbbb", "eeeeee"}


def test_cascading_reranker_degrades_on_stage_failure():
    class BrokenReranker:
        name = "broken"

        def score(self, query, documents):
            raise RuntimeError("model unavailable")

    reranker = CascadingReranker(BrokenReranker(), BrokenReranker())
    scores = reranker.score("Python Agent", ["Python Agent 经验", "无关内容"])
    assert len(scores) == 2
    assert scores[0] > scores[1]  # lexical fallback still ranks meaningfully


def test_cascade_enabled_via_settings(monkeypatch):
    monkeypatch.setenv("RERANK_STAGES_ENABLED", "true")
    get_settings.cache_clear()
    get_reranker_provider.cache_clear()
    provider = get_reranker_provider()
    assert provider.name.startswith("cascade:")


def test_cascade_disabled_returns_lexical(monkeypatch):
    monkeypatch.setenv("RERANK_STAGES_ENABLED", "false")
    monkeypatch.setenv("RETRIEVAL_PROVIDER", "hash")
    get_settings.cache_clear()
    get_reranker_provider.cache_clear()
    assert isinstance(get_reranker_provider(), LexicalReranker)
