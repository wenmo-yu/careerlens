"""Phase 2/C: build-time solidification + query-time mode switching."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.evidence import Evidence
from app.services.knowledge import VALID_MODES, search_knowledge
from app.wiki.compiler import compile_page


@pytest.fixture
async def mode_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_invalid_mode_rejected(mode_db):
    assert set(VALID_MODES) == {"rag", "wiki", "hybrid"}
    async with mode_db() as session:
        with pytest.raises(ValueError):
            await search_knowledge(
                session, user_id="u", query="q", mode="bogus", evidence=[]
            )


async def test_rag_mode_only_returns_rag_hits(mode_db):
    async with mode_db() as session:
        evidence = [
            Evidence(
                user_id="u", source_type="resume", source_name="cv",
                content="熟悉 Python 与 FastAPI 构建 Agent。", source_metadata={},
            )
        ]
        session.add_all(evidence)
        await session.commit()
        hits, diag = await search_knowledge(
            session, user_id="u", query="Python", mode="rag", evidence=evidence
        )
        assert diag["mode"] == "rag"
        assert diag["source_kinds"] == ["rag"]
        assert all(h["source_kind"] == "rag" for h in hits)
        assert "backend" in diag  # underlying RAG diagnostics preserved


async def test_wiki_mode_only_returns_wiki_pages(mode_db):
    async with mode_db() as session:
        await compile_page(
            session, user_id="u", slug="python", title="Python 技能",
            sources=[{"evidence_id": "ev-1", "content": "熟悉 Python 与 FastAPI 构建 Agent。"}],
        )
        hits, diag = await search_knowledge(
            session, user_id="u", query="Python", mode="wiki", evidence=[]
        )
        assert diag["mode"] == "wiki"
        assert diag["wiki_count"] >= 1
        assert all(h["source_kind"] == "wiki" for h in hits)
        assert all("chunk_refs" in h for h in hits)


async def test_redacted_wiki_page_is_not_retrievable(mode_db):
    """Evidence deletion marks wiki pages redacted; those must not surface."""
    from app.models.wiki import WikiPage

    async with mode_db() as session:
        await compile_page(
            session, user_id="u", slug="python", title="Python 技能",
            sources=[{"evidence_id": "ev-1", "content": "熟悉 Python 与 FastAPI 构建 Agent。"}],
        )
        page = await session.scalar(select(WikiPage).where(WikiPage.user_id == "u"))
        assert page is not None
        page.privacy_redacted = True
        await session.commit()

        hits, diag = await search_knowledge(
            session, user_id="u", query="Python", mode="wiki", evidence=[]
        )
        assert diag["wiki_count"] == 0
        assert hits == []


async def test_hybrid_fuses_both_sources_with_multi_source_refs(mode_db):
    async with mode_db() as session:
        evidence = [
            Evidence(
                user_id="u", source_type="resume", source_name="cv",
                content="熟悉 Python 与 FastAPI 构建 Agent。", source_metadata={},
            )
        ]
        session.add_all(evidence)
        await session.commit()
        await compile_page(
            session, user_id="u", slug="agent", title="Agent 方向",
            sources=[{"evidence_id": "ev-wiki", "content": "目标是从事 AI Agent 应用开发。"}],
        )
        hits, diag = await search_knowledge(
            session, user_id="u", query="Agent", mode="hybrid", evidence=evidence
        )
        assert diag["mode"] == "hybrid"
        assert diag["rag_count"] >= 1
        assert diag["wiki_count"] >= 1
        kinds = {h["source_kind"] for h in hits}
        assert {"rag", "wiki"} <= kinds
        # Multi-source references preserved: rag hits keep evidence ids, wiki
        # hits keep chunk_refs to stable evidence ids.
        assert any("evidence_id" in h for h in hits)
        assert any("chunk_refs" in h for h in hits)


async def test_mode_switch_requires_no_rebuild(mode_db):
    """Switching mode is a pure query strategy; no build artifacts change."""
    async with mode_db() as session:
        await compile_page(
            session, user_id="u", slug="s", title="t",
            sources=[{"evidence_id": "ev", "content": "LangGraph 多轮对话经验。"}],
        )
        rag_hits, _ = await search_knowledge(
            session, user_id="u", query="LangGraph", mode="rag", evidence=[]
        )
        wiki_hits, _ = await search_knowledge(
            session, user_id="u", query="LangGraph", mode="wiki", evidence=[]
        )
        hybrid_hits, _ = await search_knowledge(
            session, user_id="u", query="LangGraph", mode="hybrid", evidence=[]
        )
        assert rag_hits == []
        assert len(wiki_hits) >= 1
        assert len(hybrid_hits) == len(wiki_hits)


# --- API end-to-end: build via wiki route, query via chat mode ---

async def test_api_compile_then_chat_mode_switch(client):
    imported = await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "km-user",
            "source_type": "resume",
            "content": "熟悉 Python、FastAPI 与 LangGraph，目标是 Agent 应用开发。",
        },
    )
    assert imported.status_code == 201
    evidence_id = imported.json()["items"][0]["id"]

    compiled = await client.post(
        "/api/v1/wiki/compile",
        json={
            "user_id": "km-user",
            "slug": "agent",
            "title": "Agent 方向",
            "evidence_ids": [evidence_id],
        },
    )
    assert compiled.status_code == 201
    assert compiled.json()["page"]["version"] == 1
    assert compiled.json()["diagnostics"]["unknown_handles"] == []

    pages = await client.get("/api/v1/wiki", params={"user_id": "km-user"})
    assert pages.status_code == 200
    assert any(p["slug"] == "agent" for p in pages.json())

    # Chat requires a profile; build it before switching query modes.
    assert (await client.post("/api/v1/profiles/km-user/rebuild")).status_code == 200

    # Query with rag / wiki / hybrid — all work, no rebuild in between.
    for mode in ("rag", "wiki", "hybrid"):
        resp = await client.post(
            "/api/v1/chat",
            json={"user_id": "km-user", "message": "我适合什么方向？", "mode": mode},
        )
        assert resp.status_code == 200
        assert resp.json()["retrieval"]["mode"] == mode

    # Invalid mode rejected at schema validation.
    bad = await client.post(
        "/api/v1/chat",
        json={"user_id": "km-user", "message": "x", "mode": "bogus"},
    )
    assert bad.status_code == 422


async def test_wiki_revisions_restore_citations_and_delete_obsolete_sources(client):
    user_id = "wiki-lineage"
    compile_url = "/api/v1/wiki/compile"
    page_url = "/api/v1/wiki/lineage"
    query = {"user_id": user_id}
    payload = {**query, "slug": "lineage", "title": "Project notes"}
    evidence_ids = []
    for content in ("Python project", "FastAPI project"):
        result = await client.post("/api/v1/evidence/text", json={**query, "content": content})
        evidence_ids.append(result.json()["items"][0]["id"])
    first, second = evidence_ids
    unavailable = await client.post(
        compile_url, json={**payload, "evidence_ids": [first, "unavailable"]}
    )
    assert unavailable.status_code == 422
    for base, evidence_id in [(None, first), (1, second)]:
        compiled = await client.post(
            compile_url,
            json={**payload, "base_version": base, "evidence_ids": [evidence_id]},
        )
        assert compiled.status_code == 201
    conflict = await client.post(compile_url, json={**payload, "evidence_ids": [first]})
    assert conflict.status_code == 409

    rollback = await client.post(f"{page_url}/revert", json={**query, "target_version": 1})
    assert rollback.status_code == 200
    assert rollback.json()["chunk_refs"] == [first]
    assert rollback.json()["source_refs"] == [first]
    await client.delete(f"/api/v1/evidence/{second}")
    history = await client.get(f"{page_url}/revisions", params=query)
    assert all(revision["version"] != 2 for revision in history.json())
    assert (await client.get(page_url, params=query)).status_code == 200
    await client.delete(f"/api/v1/evidence/{first}")
    assert (await client.get(page_url, params=query)).status_code == 404
    exported = (await client.get(f"/api/v1/privacy/{user_id}/export")).json()
    assert exported["wiki_revisions"] == []
