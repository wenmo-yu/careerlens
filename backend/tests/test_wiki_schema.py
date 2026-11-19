"""Phase 2/A: Wiki page version invariants (aligned with WeKnora wiki_page.go)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.wiki import WikiPage, WikiRevision
from app.services.wiki_pages import (
    PIPELINE_REVISION_KEEP,
    StaleWikiWriteError,
    WikiRevisionNotFound,
    create_page,
    get_page,
    list_revisions,
    revert_page,
    update_page,
)


@pytest.fixture
async def wiki_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_version_bumps_only_on_visible_change(wiki_db):
    async with wiki_db() as session:
        page = await create_page(
            session, user_id="u", slug="python", title="Python", content="v1 body",
            edit_source="user",
        )
        assert page.version == 1

        # Bookkeeping-only write: no bump, no snapshot.
        await update_page(
            session, page=page, base_version=1, edit_source="pipeline",
            values={"title": "Python", "content": "v1 body", "summary": None,
                    "page_type": "concept", "status": "published"},
            out_links=["related"],
        )
        assert page.version == 1
        assert await session.scalar(
            select(WikiRevision).where(WikiRevision.page_id == page.id)
        ) is None

        # Visible change: bump + snapshot.
        await update_page(
            session, page=page, base_version=1, edit_source="pipeline",
            values={"title": "Python", "content": "v2 body", "summary": None,
                    "page_type": "concept", "status": "published"},
        )
        assert page.version == 2
        revisions = list(await list_revisions(session, user_id="u", page_id=page.id))
        assert len(revisions) == 1
        # Snapshot's edit_source is the SUPERSEDED version's author (user), not pipeline.
        assert revisions[0].version == 1
        assert revisions[0].edit_source == "user"
        assert revisions[0].content == "v1 body"


async def test_stale_write_is_rejected(wiki_db):
    async with wiki_db() as session:
        page = await create_page(
            session, user_id="u", slug="s", title="t", content="v1", edit_source="user"
        )
        await update_page(
            session, page=page, base_version=1, edit_source="agent",
            values={"title": "t", "content": "v2", "summary": None,
                    "page_type": "concept", "status": "published"},
        )
        with pytest.raises(StaleWikiWriteError):
            await update_page(
                session, page=page, base_version=1, edit_source="pipeline",
                values={"title": "t", "content": "stale", "summary": None,
                        "page_type": "concept", "status": "published"},
            )
        assert page.content == "v2"


async def test_stale_write_is_rejected_across_sessions(wiki_db):
    async with wiki_db() as writer, wiki_db() as old_reader:
        page = await create_page(
            writer, user_id="concurrent", slug="topic", title="Title", content="first"
        )
        await writer.commit()
        stale_page = await get_page(old_reader, user_id="concurrent", slug="topic")
        await update_page(
            writer, page=page, base_version=1, edit_source="user", values={"content": "new"}
        )
        with pytest.raises(StaleWikiWriteError):
            await update_page(
                old_reader, page=stale_page, base_version=1, edit_source="pipeline",
                values={"content": "stale"},
            )


async def test_revert_is_a_new_version_and_keeps_history(wiki_db):
    async with wiki_db() as session:
        page = await create_page(
            session, user_id="u", slug="s", title="t", content="v1", edit_source="user"
        )
        await update_page(
            session, page=page, base_version=1, edit_source="agent",
            values={"title": "t", "content": "v2", "summary": None,
                    "page_type": "concept", "status": "published"},
        )
        with pytest.raises(WikiRevisionNotFound):
            await revert_page(session, page=page, target_version=2)

        reverted = await revert_page(session, page=page, target_version=1)
        assert reverted.version == 3
        assert reverted.content == "v1"
        assert reverted.last_edit_source == "revert"
        revisions = list(await list_revisions(session, user_id="u", page_id=page.id))
        assert {r.version for r in revisions} == {1, 2}


async def test_clearing_summary_persists_and_is_noop_second_time(wiki_db):
    """WeKnora's zero-value trap: clearing a field must really write through."""
    async with wiki_db() as session:
        page = await create_page(
            session, user_id="u", slug="s", title="t", content="v1",
            summary="has summary", edit_source="user",
        )
        values = {"title": "t", "content": "v1", "summary": None,
                  "page_type": "concept", "status": "published"}
        await update_page(session, page=page, base_version=1, edit_source="user", values=values)
        assert page.version == 2
        assert page.summary is None
        # Same content again: no-op, no bump.
        await update_page(session, page=page, base_version=2, edit_source="user", values=values)
        assert page.version == 2


async def test_pipeline_revisions_pruned_before_human(wiki_db):
    async with wiki_db() as session:
        page = await create_page(
            session, user_id="u", slug="s", title="t", content="v1", edit_source="user"
        )
        ver = 1
        # Two human edits early on.
        for i in range(2):
            await update_page(
                session, page=page, base_version=ver, edit_source="user",
                values={"title": "t", "content": f"human{i}", "summary": None,
                        "page_type": "concept", "status": "published"},
            )
            ver += 1
        # Many pipeline rewrites.
        for i in range(PIPELINE_REVISION_KEEP + 4):
            await update_page(
                session, page=page, base_version=ver, edit_source="pipeline",
                values={"title": "t", "content": f"pipe{i}", "summary": None,
                        "page_type": "concept", "status": "published"},
            )
            ver += 1
        revisions = list(await list_revisions(session, user_id="u", page_id=page.id))
        sources = [r.edit_source for r in revisions]
        # Early human revisions survive; excess pipeline revisions were trimmed.
        assert "user" in sources
        assert sources.count("pipeline") <= PIPELINE_REVISION_KEEP


async def test_unique_slug_per_user(wiki_db):
    from sqlalchemy.exc import IntegrityError

    async with wiki_db() as session:
        await create_page(session, user_id="u", slug="s", title="t", content="v")
        session.add(
            WikiPage(user_id="u", slug="s", title="t2", content="v2", version=1,
                     last_edit_source="pipeline", source_refs=[], chunk_refs=[],
                     out_links=[], in_links=[], status="published")
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_get_page_by_slug(wiki_db):
    async with wiki_db() as session:
        await create_page(session, user_id="u", slug="s", title="t", content="v")
        found = await get_page(session, user_id="u", slug="s")
        assert found and found.title == "t"
        assert await get_page(session, user_id="other", slug="s") is None
