from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.models.evidence import Evidence
from app.retrieval.hybrid import hybrid_search
from app.retrieval.providers import get_embedding_provider, get_reranker_provider
from app.retrieval.qdrant_store import QdrantEvidenceStore


@lru_cache
def get_qdrant_store() -> QdrantEvidenceStore:
    settings = get_settings()
    return QdrantEvidenceStore(
        client=QdrantClient(url=settings.qdrant_url, timeout=2),
        collection_name=settings.qdrant_collection,
        embedder=get_embedding_provider(),
        reranker=get_reranker_provider(),
        prefetch_limit=settings.retrieval_prefetch_limit,
    )


async def index_evidence(evidence: list[Evidence], *, strict: bool = False) -> dict:
    settings = get_settings()
    if settings.retrieval_backend == "local":
        return {"indexed": 0, "backend": "local", "status": "skipped"}
    try:
        count = await get_qdrant_store().aindex(evidence)
        return {"indexed": count, "backend": "qdrant", "status": "ok"}
    except Exception as exc:
        if strict or settings.retrieval_backend == "qdrant":
            raise
        return {
            "indexed": 0,
            "backend": "local",
            "status": "fallback",
            "reason": type(exc).__name__,
        }


async def search_evidence(
    *, user_id: str, query: str, evidence: list[Evidence], limit: int = 5
) -> tuple[list[dict], dict]:
    settings = get_settings()
    if settings.retrieval_backend != "local":
        try:
            results = await get_qdrant_store().asearch(
                user_id=user_id,
                query=query,
                limit=limit,
            )
            if results or not evidence or settings.retrieval_backend == "qdrant":
                return results, {
                    "backend": "qdrant",
                    "fusion": "rrf",
                    "reranker": get_reranker_provider().name,
                    "fallback": False,
                }
            fallback_reason = "qdrant_empty"
        except Exception as exc:
            if settings.retrieval_backend == "qdrant":
                raise
            fallback_reason = type(exc).__name__
    else:
        fallback_reason = "configured_local"

    results = hybrid_search(query, evidence, limit=limit)
    for item in results:
        item["rerank_score"] = item["score"]
        item["retrieval_method"] = "local_dense_sparse_fallback"
    return results, {
        "backend": "local",
        "fusion": "weighted_score",
        "reranker": "lexical-v1",
        "fallback": True,
        "reason": fallback_reason,
    }


async def delete_evidence_index(evidence_id: str) -> dict:
    settings = get_settings()
    if settings.retrieval_backend == "local":
        return {"backend": "local", "status": "skipped"}
    try:
        await get_qdrant_store().adelete(evidence_id)
        return {"backend": "qdrant", "status": "deleted"}
    except Exception as exc:
        if settings.retrieval_backend == "qdrant":
            raise
        return {"backend": "local", "status": "fallback", "reason": type(exc).__name__}


async def delete_user_index(user_id: str) -> dict:
    settings = get_settings()
    if settings.retrieval_backend == "local":
        return {"backend": "local", "status": "skipped"}
    try:
        await get_qdrant_store().adelete_user(user_id)
        return {"backend": "qdrant", "status": "deleted"}
    except Exception as exc:
        if settings.retrieval_backend == "qdrant":
            raise
        return {"backend": "local", "status": "fallback", "reason": type(exc).__name__}
