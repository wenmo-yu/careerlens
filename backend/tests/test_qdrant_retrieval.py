import os
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.models.evidence import Evidence
from app.retrieval import service
from app.retrieval.hybrid import hybrid_search
from app.retrieval.providers import HashEmbeddingProvider, LexicalReranker, embedding_fingerprint
from app.retrieval.qdrant_store import IndexIncompatible, QdrantEvidenceStore, sparse_vector
from app.retrieval.service import search_evidence
from app.runtime.reindex import rebuild


def _evidence(evidence_id: str, content: str) -> Evidence:
    return Evidence(
        id=evidence_id,
        user_id="retrieval-user",
        source_type="resume",
        source_name="resume.md",
        content=content,
        chunk_index=0,
        source_metadata={},
    )


def test_sparse_vector_is_stable_and_sorted():
    first = sparse_vector("Python LangGraph Python")
    second = sparse_vector("Python LangGraph Python")
    assert first == second
    assert first.indices == sorted(first.indices)


def test_qdrant_dense_sparse_rrf_and_rerank():
    store = QdrantEvidenceStore(
        client=QdrantClient(":memory:"),
        collection_name="test_evidence",
        embedder=HashEmbeddingProvider(64),
        reranker=LexicalReranker(),
        prefetch_limit=10,
    )
    records = [
        _evidence("11111111-1111-1111-1111-111111111111", "使用 LangGraph 构建 Agent 工作流"),
        _evidence("22222222-2222-2222-2222-222222222222", "使用 React 开发数据看板"),
    ]
    assert store.index(records) == 2
    candidates = store.candidates(user_id="retrieval-user", query="LangGraph Agent", limit=2)
    results = store.rank(
        query="LangGraph Agent", candidates=candidates,
        evidence={item.id: {
            "content": item.content, "source_name": item.source_name,
            "source_type": item.source_type,
        } for item in records}, limit=2,
    )
    assert results[0]["evidence_id"] == records[0].id
    assert results[0]["retrieval_method"] == "qdrant_dense_sparse_rrf_rerank"
    assert "rerank_score" in results[0]


def test_hybrid_search_pairs_each_content_with_its_own_evidence():
    """Regression: the returned content must belong to the returned evidence_id.

    Before the fix, hybrid.py reused a loop-leftover ``content`` variable, so
    every hit carried the last record's text while its id/source pointed at the
    current record. That silently corrupted local retrieval and evaluation.
    """
    records = [
        _evidence("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "LangGraph 工作流编排与状态机实践"),
        _evidence("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "React 数据看板与图表可视化"),
        _evidence("cccccccc-cccc-cccc-cccc-cccccccccccc", "PostgreSQL 索引优化与查询计划"),
    ]
    by_id = {record.id: record.content for record in records}
    results = hybrid_search("LangGraph Agent 工作流", records, limit=3)

    assert results, "expected at least one hit"
    for hit in results:
        assert hit["content"] == by_id[hit["evidence_id"]], (
            f"content/evidence_id mismatch: {hit['evidence_id']} -> {hit['content']!r}"
        )


async def test_deleted_evidence_is_filtered_from_stale_vector_index(monkeypatch):
    class StaleIndex:
        def candidates(self, **kwargs):
            return [("deleted-evidence", 1.0)]

        def rank_with_trace(self, **kwargs):
            assert kwargs["evidence"] == {}
            return [], {"effective": "none"}

    monkeypatch.setattr(
        "app.retrieval.service.get_settings", lambda: Settings(retrieval_backend="qdrant")
    )
    monkeypatch.setattr("app.retrieval.service.get_qdrant_store", StaleIndex)
    hits, _ = await search_evidence(user_id="retrieval-user", query="content", evidence=[])
    assert hits == []


@pytest.fixture(params=["local", "server"])
def vector_client(request):
    if request.param == "local":
        return QdrantClient(":memory:")
    url = os.getenv("CAREERLENS_TEST_QDRANT_URL")
    if not url:
        pytest.skip("Set CAREERLENS_TEST_QDRANT_URL for the disposable Qdrant integration")
    client = QdrantClient(url=url, api_key=os.getenv("CAREERLENS_TEST_QDRANT_KEY"), timeout=5)
    assert client.info().version == "1.15.4"
    return client


async def test_vector_generation_and_live_tenant_authority(
    vector_client, session_factory, monkeypatch,
):
    name = f"careerlens_test_{uuid4().hex}"
    settings = Settings(qdrant_collection=name, retrieval_backend="qdrant", embedding_dimension=64)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr("app.retrieval.generations.get_settings", lambda: settings)

    class RecordingReranker(LexicalReranker):
        def score(self, query, documents):
            assert documents == ["我的项目使用 Python 做证据处理"]
            return super().score(query, documents)

    store = QdrantEvidenceStore(
        client=vector_client, collection_name=name, embedder=HashEmbeddingProvider(64),
        reranker=RecordingReranker(), fingerprint=embedding_fingerprint(settings),
    )
    monkeypatch.setattr(service, "get_qdrant_store", lambda: store)
    monkeypatch.setattr(service, "get_qdrant_client", lambda: vector_client)

    mine = _evidence(str(uuid4()), "我的项目使用 Python 做证据处理")
    unrelated = [_evidence(str(uuid4()), f"Python 高度相似 {i}") for i in range(32)]
    for item in unrelated:
        item.user_id = "other-tenant"
    stale = _evidence(str(uuid4()), "Python 已经删除的内容")
    try:
        async with session_factory.begin() as session:
            session.add_all([mine, *unrelated])
        store.ensure_collection(building=True)
        with pytest.raises(IndexIncompatible):
            store.candidates(user_id=mine.user_id, query="Python", limit=3)
        assert await rebuild(session_factory, store) == 33
        assert store.index([stale]) == 1
        raw = store.candidates(user_id=mine.user_id, query="Python", limit=3)
        assert {point for point, _ in raw} == {mine.id, stale.id}

        async with session_factory() as session:
            hits, diagnostics = await search_evidence(
                user_id=mine.user_id, query="Python", session=session, limit=3,
            )
        assert [item["evidence_id"] for item in hits] == [mine.id]
        assert diagnostics["candidate_count"] == 2 and diagnostics["validated_count"] == 1

        store.fingerprint = "different-model-at-the-same-dimension"
        with pytest.raises(IndexIncompatible):
            store.candidates(user_id=mine.user_id, query="Python", limit=3)
        with pytest.raises(IndexIncompatible):
            store.index([mine])
        settings.retrieval_backend = "local"
        assert (await service.delete_evidence_index(stale.id))["status"] == "deleted"
        assert (await service.delete_user_index(mine.user_id))["status"] == "deleted"
        assert vector_client.retrieve(name, [mine.id, stale.id]) == []
        assert len(vector_client.retrieve(name, [item.id for item in unrelated])) == 32
    finally:
        if vector_client.collection_exists(name):
            vector_client.delete_collection(name)

