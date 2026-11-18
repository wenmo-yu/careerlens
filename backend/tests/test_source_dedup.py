"""Phase 1/C: source-level dedup keyed on user_id + content_hash."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.evidence import Evidence
from app.services.evidence import create_evidence_chunks


async def _count(session_factory) -> int:
    async with session_factory() as session:
        return (await session.scalar(select(func.count()).select_from(Evidence))) or 0


async def test_reupload_same_text_reuses_evidence_and_keeps_source(client):
    payload = {
        "user_id": "dedup-user",
        "source_type": "resume",
        "source_name": "cv-v1.pdf",
        "content": "使用 Python 与 FastAPI 构建 AI Agent，熟悉 Qdrant 检索。",
    }
    first = await client.post("/api/v1/evidence/text", json=payload)
    assert first.status_code == 201
    assert first.json()["count"] == 1
    first_id = first.json()["items"][0]["id"]

    second = await client.post("/api/v1/evidence/text", json=payload)
    assert second.status_code == 201
    assert second.json()["count"] == 1
    assert second.json()["items"][0]["id"] == first_id

    # Count in DB stays at one chunk worth of evidence (short text => 1 chunk).
    listed = await client.get(
        "/api/v1/evidence", params={"user_id": "dedup-user"}
    )
    assert listed.json()["count"] == 1


async def test_same_text_from_two_sources_merges_references(client):
    content = "熟悉 LangGraph 多轮对话与证据检索架构设计。" * 3
    await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "dedup-multi",
            "source_type": "resume",
            "source_name": "resume.md",
            "content": content,
        },
    )
    await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "dedup-multi",
            "source_type": "self_statement",
            "source_name": "statement.md",
            "content": content,
        },
    )
    listed = await client.get(
        "/api/v1/evidence", params={"user_id": "dedup-multi", "limit": 500}
    )
    items = listed.json()["items"]
    # chunk_text may split long text into a few chunks; for each chunk there
    # must be exactly one row, carrying both sources.
    assert items
    for item in items:
        sources = item["source_metadata"]["sources"]
        names = {s["source_name"] for s in sources}
        assert {"resume.md", "statement.md"} <= names
        assert item["source_metadata"]["source_count"] >= 2


async def test_different_users_do_not_share_dedup(client):
    content = "相同的职业目标描述内容用于验证用户隔离。"
    await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "user-a", "content": content},
    )
    await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "user-b", "content": content},
    )
    for user in ("user-a", "user-b"):
        listed = await client.get("/api/v1/evidence", params={"user_id": user})
        assert listed.json()["count"] == 1


async def test_distinct_content_is_not_merged(client):
    await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "dedup-distinct", "content": "第一段完全不同的内容。"},
    )
    await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "dedup-distinct", "content": "第二段截然不同的内容。"},
    )
    listed = await client.get(
        "/api/v1/evidence", params={"user_id": "dedup-distinct"}
    )
    assert listed.json()["count"] == 2


@pytest.mark.asyncio
async def test_dedup_with_commit_false_keeps_transaction_open():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from app.core.database import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        first = await create_evidence_chunks(
            session,
            user_id="u",
            source_type="resume",
            source_name="a",
            content="原子事务内的去重文本",
            commit=False,
        )
        assert first and first[0].id
        second = await create_evidence_chunks(
            session,
            user_id="u",
            source_type="resume",
            source_name="b",
            content="原子事务内的去重文本",
            commit=False,
        )
        assert [r.id for r in second] == [r.id for r in first]
        await session.commit()
    assert await _count(factory) == 1
    await engine.dispose()
