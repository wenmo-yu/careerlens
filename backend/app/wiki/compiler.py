"""Compile source blocks into a source-grounded Wiki page (phase 2/B).

Flow: register stable evidence ids as short handles -> render a model prompt ->
generate page content with handle citations -> resolve handles back to stable
ids (dropping unknowns) -> guard against silently dropped table rows -> write
through the versioned page service under optimistic concurrency.

Without a configured model, a deterministic fallback builds a traceable page
from the supplied blocks, so compilation works in local demos and tests.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_llm_provider
from app.llm.provider import model_fallback
from app.models.evidence import Evidence
from app.models.wiki import WikiPage
from app.runtime.store import check_write_scope, read_scope
from app.services.wiki_pages import (
    StaleWikiWriteError,
    create_compiled_page,
    get_page,
    update_page,
)
from app.wiki.handles import HandleTable
from app.wiki.tables import DroppedTableRowsError, assert_rows_preserved

COMPILE_SCHEMA = {
    "type": "object",
    "required": ["title", "content", "summary", "citations"],
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string", "description": "Markdown with [c000] inline citations"},
        "summary": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Handles of sources supporting this page",
        },
    },
}


class WikiCompileError(Exception):
    """Compilation could not produce an acceptable page."""


def _deterministic_page(
    title: str, sources: list[dict[str, Any]], handles: HandleTable
) -> dict[str, Any]:
    """Build a traceable page without a model: concatenate blocks + cite all."""
    parts: list[str] = []
    for source in sources:
        handle = handles.handle(source["evidence_id"])
        parts.append(f"{source['content'].strip()}\n\n[{handle}]")
    content = "\n\n".join(parts)
    return {
        "title": title,
        "summary": f"由 {len(sources)} 条证据编译，所有引用均可回溯。",
        "content": content,
        "citations": [handles.handle(s["evidence_id"]) for s in sources],
    }


def resolve_citations(
    citations: list[str], handles: HandleTable
) -> list[str]:
    """Resolve model-produced handles to stable evidence ids, dropping unknowns."""
    resolved: list[str] = []
    for handle in citations:
        stable = handles.resolve(handle)
        if stable is not None and stable not in resolved:
            resolved.append(stable)
    return resolved


async def _generate(
    *, title: str, sources: list[dict[str, Any]], handles: HandleTable
) -> tuple[dict[str, Any], dict]:
    provider = get_llm_provider("wiki")
    diagnostics = provider.diagnostics
    if diagnostics["provider"] == "demo":
        return _deterministic_page(title, sources, handles), diagnostics

    rendered = "\n\n".join(
        handles.render_block(
            handles.handle(source["evidence_id"]), index, source["content"]
        )
        for index, source in enumerate(sources)
    )
    try:
        raw = await provider.generate_json(
            system_prompt=(
                "你是职业画像 Wiki 编译器。把给定证据整理成一页结构化的 Markdown 专题页。"
                "引用证据时只使用 <c id=\"...\"> 里的短句柄，例如 [c000]，不要发明句柄。"
                "不要删除或压缩表格中的任何行。"
            ),
            user_prompt=f"专题标题：{title}\n\n证据：\n{rendered}",
            schema=COMPILE_SCHEMA,
            operation="wiki_compile",
        )
        page = {
            "title": str(raw.get("title") or title),
            "content": str(raw.get("content") or ""),
            "summary": raw.get("summary"),
            "citations": [str(h) for h in raw.get("citations", [])],
        }
    except Exception as exc:
        # A model failure degrades to a deterministic, still traceable page.
        page = _deterministic_page(title, sources, handles)
        diagnostics = model_fallback(provider, exc, "wiki_compile")
    return page, diagnostics


async def compile_page(
    session: AsyncSession,
    *,
    user_id: str,
    slug: str,
    title: str,
    sources: list[dict[str, Any]],
    base_version: int | None = None,
    edit_source: str = "pipeline",
    source_refs: list[str] | None = None,
    commit: bool = True,
    verify_sources: bool = False,
) -> tuple[WikiPage, dict]:
    """Compile sources into a page and write it through the guarded write path.

    ``sources`` items: ``{"evidence_id": str, "content": str}``. ``base_version``
    is the version the caller last saw; pass ``None`` only to create a new page.
    """
    source_ids = list(dict.fromkeys(source["evidence_id"] for source in sources))
    refs = source_ids if source_refs is None else source_refs
    generation = await read_scope(session, user_id)
    await check_page_version(session, user_id, slug, base_version)
    values, chunk_refs, diagnostics = await prepare_page(title, sources)
    await check_write_scope(session, user_id, expected=generation)
    page = await persist_page(
        session, user_id=user_id, slug=slug, values=values, base_version=base_version,
        edit_source=edit_source, source_refs=refs, chunk_refs=chunk_refs,
        verify_sources=verify_sources,
    )
    if commit:
        await session.commit()
    return page, diagnostics


async def check_page_version(
    session: AsyncSession, user_id: str, slug: str, base_version: int | None
) -> WikiPage | None:
    existing = await get_page(session, user_id=user_id, slug=slug)
    expected = existing.version if existing is not None else None
    if base_version != expected:
        raise StaleWikiWriteError(
            f"page version changed: expected {base_version}, found {expected}"
        )
    return existing


async def prepare_page(title: str, sources: list[dict[str, Any]]) -> tuple[dict, list[str], dict]:
    if not sources:
        raise WikiCompileError("no sources to compile")
    source_ids = list(dict.fromkeys(source["evidence_id"] for source in sources))
    handles = HandleTable()
    for source in sources:
        handles.register(source["evidence_id"])

    generated, diagnostics = await _generate(title=title, sources=sources, handles=handles)

    # Resolve handle citations to stable ids; unknown handles are discarded.
    chunk_refs = resolve_citations(generated["citations"], handles)
    content = handles.strip_inline_citations(generated["content"])
    if not content or not chunk_refs:
        if diagnostics["provider"] != "demo":
            diagnostics = model_fallback(
                get_llm_provider("wiki"), ValueError("Missing citations"), "wiki_compile",
            )
        generated = _deterministic_page(title, sources, handles)
        chunk_refs = source_ids
        content = handles.strip_inline_citations(generated["content"])

    # Guard: no source table rows may silently vanish in the rewrite.
    try:
        assert_rows_preserved(
            "",
            content,
            source_tables=[s["content"] for s in sources if "|" in s.get("content", "")],
        )
    except DroppedTableRowsError as exc:
        raise WikiCompileError(str(exc)) from exc

    values = {
        "title": (generated["title"] or title)[:255],
        "content": content,
        "summary": str(generated["summary"]) if generated.get("summary") is not None else None,
        "page_type": "concept",
        "status": "published",
    }
    return values, chunk_refs, {**diagnostics, "unknown_handles": handles.unknown_handles}


async def persist_page(
    session: AsyncSession, *, user_id: str, slug: str, values: dict, base_version: int | None,
    edit_source: str, source_refs: list[str], chunk_refs: list[str], verify_sources: bool,
) -> WikiPage:
    existing = await check_page_version(session, user_id, slug, base_version)
    if verify_sources:
        live_ids = set(await session.scalars(
            select(Evidence.id)
            .where(Evidence.user_id == user_id, Evidence.id.in_(source_refs))
            .order_by(Evidence.id)
            .with_for_update()
        ))
        if live_ids != set(source_refs):
            raise WikiCompileError("One or more evidence sources are unavailable")

    if existing is None:
        return await create_compiled_page(
            session,
            user_id=user_id,
            slug=slug,
            values={
                **values,
                "last_edit_source": edit_source,
                "source_refs": source_refs,
                "chunk_refs": chunk_refs,
            },
        )
    return await update_page(
        session,
        page=existing,
        base_version=base_version,
        edit_source=edit_source,
        values=values,
        source_refs=source_refs,
        chunk_refs=chunk_refs,
        commit=False,
    )
