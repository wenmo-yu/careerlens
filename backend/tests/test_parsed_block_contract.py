"""Tests for the phase-one parsing contract and its persisted models."""

import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — register all models on Base.metadata
from app.core.database import Base
from app.ingestion.contract import (
    ParsedBlock,
    ParsedDocument,
    content_fingerprint,
    source_fingerprint,
)
from app.models.parsed_block import ParsedBlock as ParsedBlockModel
from app.models.source_document import SourceDocument


def test_fingerprints_are_stable_and_normalize_newlines():
    assert content_fingerprint("a\r\nb\n") == content_fingerprint("a\nb")
    assert content_fingerprint(" a ") == content_fingerprint("a")
    assert content_fingerprint("x") != content_fingerprint("y")
    assert source_fingerprint(b"abc") == source_fingerprint(b"abc")
    assert source_fingerprint(b"abc") != source_fingerprint(b"abd")


def test_parsed_document_contract_locations_and_hashes():
    block = ParsedBlock(
        content="| 技能 | 级别 |\n| --- | --- |\n| Python | 5 |",
        block_type="table",
        block_index=2,
        page_no=7,
        bbox={"x0": 10, "y0": 20, "x1": 300, "y1": 90},
        section_path="附录 > 技能表",
        source_type="pdf_text_layer",
        source_metadata={"filename": "cv.pdf"},
    )
    doc = ParsedDocument(
        doc_id=str(uuid.uuid4()),
        blocks=[block],
        source_type="pdf",
        metadata={"page_count": 20},
    )
    assert block.content_hash == content_fingerprint(block.content)
    assert doc.markdown == block.content
    assert len(doc.source_hash) == 64
    assert doc.metadata["page_count"] == 20
    assert block.page_no == 7
    assert block.bbox["x1"] == 300


def test_two_blocks_same_content_share_content_hash_but_distinct_evidence_ids():
    a = ParsedBlock(content="相同段落", source_type="resume")
    b = ParsedBlock(content="相同段落", source_type="self_intro")
    assert a.content_hash == b.content_hash
    assert a.evidence_id != b.evidence_id


@pytest.mark.asyncio
async def test_new_tables_created_with_constraints_and_defaults():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    assert {"source_documents", "parsed_blocks"} <= set(tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        doc = SourceDocument(
            user_id="u1",
            source_hash=source_fingerprint(b"raw"),
            filename="cv.pdf",
            source_type="pdf",
            page_count=3,
        )
        session.add(doc)
        await session.flush()
        block = ParsedBlockModel(
            evidence_id=str(uuid.uuid4()),
            doc_id=doc.id,
            user_id="u1",
            block_index=0,
            block_type="text",
            content="使用 Python 与 FastAPI 构建 Agent",
            content_hash=content_fingerprint("使用 Python 与 FastAPI 构建 Agent"),
            page_no=1,
            char_start=0,
            char_end=20,
            source_type="pdf_text_layer",
        )
        session.add(block)
        await session.commit()
        assert doc.id and doc.parse_status == "parsed"
        assert block.id and block.content_revision == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_parsed_block_doc_index_unique_constraint():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    evidence_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add_all(
            [
                ParsedBlockModel(
                    evidence_id=evidence_id,
                    doc_id="doc-1",
                    user_id="u1",
                    block_index=0,
                    block_type="text",
                    content="a",
                    content_hash=content_fingerprint("a"),
                ),
                ParsedBlockModel(
                    evidence_id=evidence_id,
                    doc_id="doc-1",
                    user_id="u1",
                    block_index=0,
                    block_type="text",
                    content="b",
                    content_hash=content_fingerprint("b"),
                ),
            ]
        )
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()
