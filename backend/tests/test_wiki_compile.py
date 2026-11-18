"""Phase 2/B: short-handle citation mapping and guarded Wiki compilation."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.services.wiki_pages import get_page
from app.wiki.compiler import WikiCompileError, compile_page, resolve_citations
from app.wiki.handles import HandleTable
from app.wiki.tables import (
    DroppedTableRowsError,
    assert_rows_preserved,
    row_identity_loss_ratio,
    table_row_identities,
)


def test_handle_table_register_resolve_and_unknown():
    handles = HandleTable()
    h0 = handles.register("ev-alpha")
    h1 = handles.register("ev-beta")
    assert h0 == "c000" and h1 == "c001"
    assert handles.register("ev-alpha") == h0  # idempotent
    assert handles.handle("ev-beta") == h1
    assert handles.resolve("c000") == "ev-alpha"
    assert handles.resolve("c999") is None
    assert handles.resolve("not-a-handle") is None
    assert "c999" in handles.unknown_handles
    assert "not-a-handle" in handles.unknown_handles


def test_strip_inline_citations_removes_only_handle_markers():
    handles = HandleTable()
    text = "正文保留。 [c000, c001]\n表格 | A | B | 保留。"
    stripped = handles.strip_inline_citations(text)
    assert "[c000" not in stripped
    assert "正文保留。" in stripped
    assert "| A | B |" in stripped


def test_resolve_citations_drops_unknown_and_dedupes():
    handles = HandleTable()
    handles.register("ev-1")
    handles.register("ev-2")
    resolved = resolve_citations(["c000", "c999", "c000", "c001"], handles)
    assert resolved == ["ev-1", "ev-2"]
    assert "c999" in handles.unknown_handles


def test_table_row_identity_and_loss_ratio():
    original = "| 技能 | 级别 |\n| --- | --- |\n| Python | 5 |\n| FastAPI | 4 |"
    assert table_row_identities(original) == ["Python", "FastAPI"]
    dropped = "| 技能 | 级别 |\n| --- | --- |\n| Python | 5 |"
    assert row_identity_loss_ratio(original, dropped) == 0.5
    with pytest.raises(DroppedTableRowsError):
        assert_rows_preserved("", dropped, source_tables=[original])
    # Zero loss passes.
    assert_rows_preserved("", original, source_tables=[original])


@pytest.fixture
async def compile_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_compile_creates_page_with_stable_citations(compile_db):
    sources = [
        {"evidence_id": "ev-resume", "content": "熟悉 Python 与 FastAPI 构建 Agent。"},
        {"evidence_id": "ev-statement", "content": "目标是从事 AI Agent 应用开发。"},
    ]
    async with compile_db() as session:
        page, diagnostics = await compile_page(
            session, user_id="u", slug="agent", title="Agent 方向", sources=sources
        )
        assert page.version == 1
        assert set(page.chunk_refs) == {"ev-resume", "ev-statement"}
        assert "[c000]" not in page.content  # inline handles stripped
        assert diagnostics["unknown_handles"] == []
        found = await get_page(session, user_id="u", slug="agent")
        assert found and found.title == "Agent 方向"


async def test_compile_rejects_stale_base_version(compile_db):
    sources = [{"evidence_id": "ev-1", "content": "第一段内容。"}]
    async with compile_db() as session:
        page, _ = await compile_page(
            session, user_id="u", slug="s", title="t", sources=sources, base_version=None
        )
        with pytest.raises(WikiCompileError):
            await compile_page(
                session, user_id="u", slug="s", title="t2", sources=sources,
                base_version=99,
            )


async def test_compile_with_model_unknown_handles_dropped(compile_db, monkeypatch):
    class FakeProvider:
        @property
        def diagnostics(self):
            return {"provider": "fake", "model": "test"}

        async def generate_json(
            self, *, system_prompt, user_prompt, schema, operation="generation"
        ):
            return {
                "title": "模型生成的标题",
                "content": "模型正文 [c000] 与伪造 [c999]。",
                "summary": "摘要",
                "citations": ["c000", "c999"],
            }

    monkeypatch.setattr("app.wiki.compiler.get_llm_provider", lambda *a, **k: FakeProvider())
    sources = [{"evidence_id": "ev-real", "content": "真实证据内容。"}]
    async with compile_db() as session:
        page, diagnostics = await compile_page(
            session, user_id="u", slug="s", title="t", sources=sources
        )
        assert page.chunk_refs == ["ev-real"]  # c999 dropped
        assert "c999" in diagnostics["unknown_handles"]
        assert "[c000]" not in page.content


async def test_compile_rejects_dropped_table_rows(compile_db, monkeypatch):
    table = "| 技能 | 级别 |\n| --- | --- |\n| Python | 5 |\n| FastAPI | 4 |"

    class DropRowsProvider:
        @property
        def diagnostics(self):
            return {"provider": "fake", "model": "drop-rows"}

        async def generate_json(
            self, *, system_prompt, user_prompt, schema, operation="generation"
        ):
            return {
                "title": "t",
                "content": "| 技能 | 级别 |\n| --- | --- |\n| Python | 5 |",
                "summary": "",
                "citations": ["c000"],
            }

    monkeypatch.setattr("app.wiki.compiler.get_llm_provider", lambda *a, **k: DropRowsProvider())
    sources = [{"evidence_id": "ev-table", "content": table}]
    async with compile_db() as session:
        with pytest.raises(WikiCompileError, match="table rows"):
            await compile_page(session, user_id="u", slug="s", title="t", sources=sources)
