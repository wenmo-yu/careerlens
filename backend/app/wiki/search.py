"""Wiki-side retrieval for query-time mode switching.

Wiki pages are the build-time-solidified knowledge product. At query time we
treat each page's Markdown as retrievable text via the existing local hybrid
search (no second Qdrant collection needed — a page is small and its evidence
links are already stable ids). Results carry the page identity and its grounded
evidence refs so the UI can expand a Wiki hit back to original Evidence.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki import WikiPage
from app.retrieval.hybrid import hybrid_search


def _wiki_hit(page: WikiPage, score: float, snippet: str) -> dict:
    return {
        "page_id": page.id,
        "slug": page.slug,
        "title": page.title,
        "content": snippet,
        "score": round(score, 4),
        "chunk_refs": list(page.chunk_refs),
        "source_refs": list(page.source_refs),
        "source_kind": "wiki",
        "retrieval_method": "wiki_page_hybrid",
    }


async def search_wiki_pages(
    session: AsyncSession, *, user_id: str, query: str, limit: int = 5
) -> list[dict]:
    pages = list(
        await session.scalars(
            select(WikiPage).where(
                WikiPage.user_id == user_id,
                WikiPage.status == "published",
            )
        )
    )
    if not pages:
        return []

    # Feed page bodies through the same local hybrid scorer used for evidence.
    scored = hybrid_search(
        query,
        [
            {
                "id": page.id,
                "content": f"{page.title}\n{page.content}",
                "source_type": "wiki_page",
                "source_name": page.slug,
            }
            for page in pages
        ],
        limit=limit,
    )
    by_id = {page.id: page for page in pages}
    hits: list[dict] = []
    for item in scored:
        page = by_id.get(item["evidence_id"])
        if page is None:
            continue
        hits.append(_wiki_hit(page, item["score"], item["content"]))
    return hits
