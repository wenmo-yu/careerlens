"""Unified knowledge retrieval with query-time mode switching.

Build time is where products are solidified: importing evidence builds the RAG
index; compiling a Wiki page builds the wiki product (both may be built). At
query time the caller picks a mode freely — no rebuild, no dual build-state:

- ``rag``: evidence retrieval only
- ``wiki``: compiled page retrieval only
- ``hybrid``: interleaved by rank, each hit tagged with source_kind so the
  UI can show and expand RAG blocks and Wiki pages separately (multi-source refs)
"""

from itertools import zip_longest
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.retrieval.service import search_evidence
from app.wiki.search import search_wiki_pages

VALID_MODES = ("rag", "wiki", "hybrid")


def _rag_hits(results: list[dict]) -> list[dict]:
    hits: list[dict] = []
    for item in results:
        hit = dict(item)
        hit["source_kind"] = "rag"
        hit.setdefault("score", hit.get("rerank_score", 0.0))
        hits.append(hit)
    return hits


async def search_knowledge(
    session: AsyncSession,
    *,
    user_id: str,
    query: str,
    mode: str,
    evidence: list[Evidence],
    limit: int = 5,
) -> tuple[list[dict], dict[str, Any]]:
    if mode not in VALID_MODES:
        raise ValueError(f"invalid knowledge mode: {mode}")

    rag_hits: list[dict] = []
    wiki_hits: list[dict] = []
    rag_diag: dict[str, Any] = {}

    if mode in ("rag", "hybrid"):
        rag_results, rag_diag = await search_evidence(
            user_id=user_id, query=query, evidence=evidence, limit=limit
        )
        rag_hits = _rag_hits(rag_results)

    if mode in ("wiki", "hybrid"):
        wiki_hits = await search_wiki_pages(
            session, user_id=user_id, query=query, limit=limit
        )

    if mode == "rag":
        hits = rag_hits
    elif mode == "wiki":
        hits = wiki_hits
    else:
        hits = [
            hit for pair in zip_longest(rag_hits, wiki_hits) for hit in pair if hit is not None
        ][:limit]

    diagnostics: dict[str, Any] = {
        "mode": mode,
        "rag_count": len(rag_hits),
        "wiki_count": len(wiki_hits),
        "source_kinds": sorted({h["source_kind"] for h in hits}),
    }
    # Preserve the underlying RAG diagnostics (backend/fusion/reranker/...) so
    # existing consumers — and the chat retrieval panel — keep working.
    if mode == "hybrid":
        diagnostics["knowledge_fusion"] = "rank_interleave"
    if rag_diag:
        diagnostics = {**rag_diag, **diagnostics}
    return hits, diagnostics
