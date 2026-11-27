import asyncio
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.evidence import Evidence
from app.retrieval.hybrid import hybrid_search
from app.retrieval.providers import (
    embedding_fingerprint,
    get_embedding_provider,
    get_reranker_provider,
)
from app.retrieval.qdrant_store import QdrantEvidenceStore, delete_points

MAX_TOP_K = 20


class RetrievalUnavailable(RuntimeError):
    pass


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2)


@lru_cache
def get_qdrant_store() -> QdrantEvidenceStore:
    settings = get_settings()
    return QdrantEvidenceStore(
        client=get_qdrant_client(),
        collection_name=settings.qdrant_collection,
        embedder=get_embedding_provider(),
        reranker=get_reranker_provider(),
        prefetch_limit=settings.retrieval_prefetch_limit,
        fingerprint=embedding_fingerprint(settings),
    )


async def index_evidence(evidence: list[Evidence], *, strict: bool = False) -> dict:
    settings = get_settings()
    if settings.retrieval_backend == "local":
        return {"indexed": 0, "backend": "local", "status": "skipped"}
    try:
        store = await asyncio.to_thread(get_qdrant_store)
        count = await store.aindex(evidence)
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
    *, user_id: str, query: str, evidence: list[Evidence] | list[dict[str, Any]] | None = None,
    session: AsyncSession | None = None, limit: int = 5,
) -> tuple[list[dict], dict]:
    settings = get_settings()
    limit = min(MAX_TOP_K, max(1, limit))
    if not query.strip() or len(query) > 2000:
        raise ValueError("Search query must contain 1–2000 characters")
    if settings.retrieval_backend != "local":
        try:
            store = await asyncio.to_thread(get_qdrant_store)
            candidates = await asyncio.to_thread(
                store.candidates, user_id=user_id, query=query, limit=limit,
            )
            candidate_ids = {point for point, _ in candidates}
            rows = evidence or []
            if session is not None:
                rows = list(await session.scalars(select(Evidence).where(
                    Evidence.user_id == user_id, Evidence.id.in_(candidate_ids),
                )))
            live = {
                value["id"]: value for value in _evidence_rows(rows, user_id)
                if value["id"] in candidate_ids
            }
            results, trace = await asyncio.to_thread(
                store.rank_with_trace, query=query, candidates=candidates, evidence=live,
                limit=limit, allow_fallback=settings.retrieval_backend != "qdrant",
            )
            if results or settings.retrieval_backend == "qdrant" or (
                session is None and not evidence
            ):
                return results, {
                    "backend": "qdrant",
                    "fusion": "rrf",
                    "reranker": trace["effective"],
                    "rerank": trace,
                    "fallback": bool(trace.get("fallback_reason")),
                    "candidate_count": len(candidates),
                    "validated_count": len(live),
                }
            fallback_reason = "qdrant_empty"
        except Exception as exc:
            if settings.retrieval_backend == "qdrant":
                raise RetrievalUnavailable("Vector retrieval is unavailable") from exc
            fallback_reason = type(exc).__name__
    else:
        fallback_reason = "configured_local"

    budget = settings.retrieval_local_row_limit
    rows = evidence or []
    if session is not None:
        rows = list(await session.scalars(select(Evidence).where(
            Evidence.user_id == user_id,
        ).order_by(Evidence.created_at.desc(), Evidence.id).limit(budget + 1)))
    partial = len(rows) > budget
    results = hybrid_search(query, _evidence_rows(rows[:budget], user_id), limit=limit)
    for item in results:
        item["rerank_score"] = item["score"]
        item["retrieval_method"] = "local_lexical_rrf_v1"
    return results, {
        "backend": "local",
        "fusion": "local_lexical_rrf_v1",
        "reranker": "lexical-v1",
        "fallback": settings.retrieval_backend != "local",
        "reason": fallback_reason,
        "partial_coverage": partial,
    }


def _evidence_rows(rows, user_id: str) -> list[dict]:
    return [
        row if isinstance(row, dict) else {
            "id": row.id, "source_type": row.source_type, "source_name": row.source_name,
            "content": row.content,
        }
        for row in rows
        if (row.get("user_id", user_id) if isinstance(row, dict) else row.user_id) == user_id
    ]


async def delete_evidence_index(
    evidence_id: str, *, strict: bool = False, collections: tuple[str, ...] | None = None,
) -> dict:
    settings = get_settings()
    try:
        client = await asyncio.to_thread(get_qdrant_client)
        for collection in collections or settings.cleanup_collections:
            await asyncio.to_thread(delete_points, client, collection, evidence_id=evidence_id)
        return {"backend": "qdrant", "status": "deleted"}
    except Exception as exc:
        if strict or settings.retrieval_backend == "qdrant":
            raise
        return {"backend": "local", "status": "fallback", "reason": type(exc).__name__}


async def delete_user_index(user_id: str, *, collection: str | None = None) -> dict:
    settings = get_settings()
    try:
        client = await asyncio.to_thread(get_qdrant_client)
        for target in (collection,) if collection else settings.cleanup_collections:
            await asyncio.to_thread(delete_points, client, target, user_id=user_id)
        return {"backend": "qdrant", "status": "deleted"}
    except Exception as exc:
        if settings.retrieval_backend == "qdrant":
            raise
        return {"backend": "local", "status": "fallback", "reason": type(exc).__name__}
