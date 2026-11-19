"""Wiki page writes with WeKnora-style version invariants.

The write path is the single choke point for all page mutations (pipeline
compiler, agent, human edits, rollback), so the invariants hold everywhere:
version bumps only on visible or citation changes, the superseded version is
snapshotted with its author, stale writes are rejected, and machine revisions are pruned
before human ones.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.wiki import WikiPage, WikiRevision
from app.services.evidence import insert_no_conflict

# User-visible fields; citation changes are also versioned.
VISIBLE_FIELDS = ("title", "content", "summary", "page_type", "status")
# Revisions kept per page: keep this many recent pipeline snapshots, and keep
# human/agent/revert revisions up to a larger hard cap.
PIPELINE_REVISION_KEEP = 5
REVISION_HARD_CAP = 50
HUMAN_EDIT_SOURCES = {"user", "agent", "revert"}


class StaleWikiWriteError(Exception):
    """base_version did not match — a newer write won the race."""


class WikiRevisionNotFound(Exception):
    """Requested rollback target version does not exist."""


def _changed_visible(page: WikiPage, values: dict) -> bool:
    return any(getattr(page, field) != value for field, value in values.items())


def _snapshot(page: WikiPage) -> WikiRevision:
    """Snapshot the current (about-to-be-superseded) page state."""
    return WikiRevision(
        page_id=page.id,
        user_id=page.user_id,
        version=page.version,
        title=page.title,
        page_type=page.page_type,
        content=page.content,
        summary=page.summary,
        status=page.status,
        source_refs=list(page.source_refs),
        chunk_refs=list(page.chunk_refs),
        # The author of the version being replaced, not the incoming writer.
        edit_source=page.last_edit_source,
    )


async def _prune_revisions(session: AsyncSession, page_id: str) -> None:
    rows = list(
        await session.scalars(
            select(WikiRevision)
            .where(WikiRevision.page_id == page_id)
            .order_by(WikiRevision.version.desc())
        )
    )
    pipeline = [r for r in rows if r.edit_source not in HUMAN_EDIT_SOURCES]
    excess_pipeline = set(pipeline[PIPELINE_REVISION_KEEP:])
    retained = [revision for revision in rows if revision not in excess_pipeline]
    overflow = max(0, len(retained) - REVISION_HARD_CAP)
    priorities = sorted(
        retained, key=lambda item: (item.edit_source in HUMAN_EDIT_SOURCES, item.version)
    )
    for revision in excess_pipeline.union(priorities[:overflow]):
        await session.delete(revision)


async def create_page(
    session: AsyncSession,
    *,
    user_id: str,
    slug: str,
    title: str,
    content: str,
    edit_source: str = "pipeline",
    summary: str | None = None,
    page_type: str = "concept",
    status: str = "published",
    source_refs: list | None = None,
    chunk_refs: list | None = None,
    out_links: list | None = None,
) -> WikiPage:
    page = WikiPage(
        user_id=user_id,
        slug=slug,
        title=title,
        page_type=page_type,
        content=content,
        summary=summary,
        version=1,
        last_edit_source=edit_source,
        source_refs=source_refs or [],
        chunk_refs=chunk_refs or [],
        out_links=out_links or [],
        status=status,
    )
    session.add(page)
    await session.flush()
    return page


async def create_compiled_page(
    session: AsyncSession,
    *,
    user_id: str,
    slug: str,
    values: dict,
) -> WikiPage:
    statement = insert_no_conflict(
        session, WikiPage, {**values, "user_id": user_id, "slug": slug}, ["user_id", "slug"]
    )
    page = await session.scalar(statement.returning(WikiPage))
    if page is None:
        raise StaleWikiWriteError("page version changed: page already exists")
    return page


async def update_page(
    session: AsyncSession,
    *,
    page: WikiPage,
    base_version: int | None,
    edit_source: str,
    values: dict,
    source_refs: list | None = None,
    chunk_refs: list | None = None,
    out_links: list | None = None,
    in_links: list | None = None,
    commit: bool = True,
) -> WikiPage:
    """Apply a write to a page under optimistic concurrency.

    ``base_version`` is the version the caller read. If it no longer matches,
    the write is stale and rejected — an old compiler run cannot clobber a
    newer page. Pass ``base_version=None`` to skip the guard (human edits).
    """
    if base_version is not None and page.version != base_version:
        raise StaleWikiWriteError(
            f"page version changed: expected {base_version}, found {page.version}"
        )

    visible = {field: values[field] for field in VISIBLE_FIELDS if field in values}
    changed = _changed_visible(page, visible)
    provenance_changed = (
        source_refs is not None and source_refs != page.source_refs
        or chunk_refs is not None and chunk_refs != page.chunk_refs
    )
    snapshot = _snapshot(page) if changed or provenance_changed else None
    updates = {**visible, "updated_at": datetime.now(UTC)}
    for field, value in (
        ("source_refs", source_refs), ("chunk_refs", chunk_refs),
        ("out_links", out_links), ("in_links", in_links),
    ):
        if value is not None:
            updates[field] = value
    if snapshot is not None:
        updates.update(version=page.version + 1, last_edit_source=edit_source)
    updated = await session.scalar(
        update(WikiPage)
        .where(WikiPage.id == page.id, WikiPage.version == page.version)
        .values(**updates)
        .returning(WikiPage.id)
        .execution_options(synchronize_session=False)
    )
    if updated is None:
        raise StaleWikiWriteError(f"page version changed: expected {page.version}")
    if snapshot is not None:
        session.add(snapshot)
        await session.flush()
        await _prune_revisions(session, page.id)
    if commit:
        await session.commit()
    await session.refresh(page)
    return page


async def revert_page(
    session: AsyncSession, *, page: WikiPage, target_version: int
) -> WikiPage:
    """Revert to a revision as an ordinary edit: new version, history kept."""
    revision = await session.scalar(
        select(WikiRevision).where(
            WikiRevision.page_id == page.id,
            WikiRevision.version == target_version,
        )
    )
    if revision is None:
        raise WikiRevisionNotFound(f"no revision {target_version} for page {page.id}")
    if revision.source_refs is None or revision.chunk_refs is None:
        raise WikiRevisionNotFound("this legacy revision has no verifiable source lineage")
    source_ids = set(revision.source_refs + revision.chunk_refs)
    if source_ids:
        existing = set(await session.scalars(
            select(Evidence.id)
            .where(Evidence.user_id == page.user_id, Evidence.id.in_(source_ids))
            .order_by(Evidence.id)
            .with_for_update()
        ))
        if existing != source_ids:
            raise WikiRevisionNotFound("this revision references unavailable evidence")
    if target_version == page.version:
        # Reverting to current is a no-op target; treat as not found to avoid a
        # misleading no-change version bump.
        raise WikiRevisionNotFound("cannot revert to the current version")
    return await update_page(
        session,
        page=page,
        base_version=page.version,
        edit_source="revert",
        values={
            "title": revision.title,
            "content": revision.content,
            "summary": revision.summary,
            "page_type": revision.page_type,
            "status": revision.status,
        },
        source_refs=revision.source_refs,
        chunk_refs=revision.chunk_refs,
    )


async def get_page(
    session: AsyncSession, *, user_id: str, slug: str
) -> WikiPage | None:
    return await session.scalar(
        select(WikiPage).where(WikiPage.user_id == user_id, WikiPage.slug == slug)
    )


async def list_pages(
    session: AsyncSession, *, user_id: str, limit: int = 50
) -> list[WikiPage]:
    result = await session.scalars(
        select(WikiPage)
        .where(WikiPage.user_id == user_id)
        .order_by(WikiPage.updated_at.desc())
        .limit(limit)
    )
    return list(result)


async def list_revisions(
    session: AsyncSession, *, user_id: str, page_id: str
) -> list[WikiRevision]:
    result = await session.scalars(
        select(WikiRevision)
        .where(WikiRevision.user_id == user_id, WikiRevision.page_id == page_id)
        .order_by(WikiRevision.version.desc())
    )
    return list(result)


async def revision_count(session: AsyncSession, *, page_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(WikiRevision).where(WikiRevision.page_id == page_id)
        )
        or 0
    )
