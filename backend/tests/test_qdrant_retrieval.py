from qdrant_client import QdrantClient

from app.models.evidence import Evidence
from app.retrieval.hybrid import hybrid_search
from app.retrieval.providers import HashEmbeddingProvider, LexicalReranker
from app.retrieval.qdrant_store import QdrantEvidenceStore, sparse_vector


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
    results = store.search(user_id="retrieval-user", query="LangGraph Agent", limit=2)
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

