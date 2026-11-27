import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, bindparam, create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
from app.migration_runner import run_migrations
from app.models.account_deletion import AccountDeletionReceipt
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.parsed_block import ParsedBlock
from app.models.source_document import SourceDocument


def _head_revision() -> str:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    return script.get_current_head()


def test_alembic_upgrade_creates_current_schema(tmp_path):
    database_path = tmp_path / "migration.db"
    async_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    run_migrations(async_url)
    run_migrations(async_url)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "access_tokens",
        "account_deletion_receipts",
        "agent_runs",
        "audit_events",
        "career_reports",
        "conversation_threads",
        "conversation_messages",
        "evaluation_runs",
        "evidence",
        "evidence_index_work",
        "deletion_work",
        "index_generations",
        "job_analyses",
        "parsed_blocks",
        "profile_items",
        "profile_update_proposals",
        "run_events",
        "run_scopes",
        "run_steps",
        "source_documents",
        # HY4-C/D
        "saved_jobs",
        "learning_progress",
        "assessment_results",
        "user_constraints",
        "dimension_definitions",
        "profile_extensions",
    } <= tables
    with engine.connect() as connection:
        revision = connection.scalar(text("select version_num from alembic_version"))
    assert revision == _head_revision()
    engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_previous_revision_upgrades_live_records(tmp_path, dialect):
    if dialect == "postgresql":
        url = os.getenv("CAREERLENS_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Set CAREERLENS_TEST_POSTGRES_URL to an empty test database")
    else:
        url = f"sqlite+aiosqlite:///{(tmp_path / 'previous.db').as_posix()}"
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, "d0e1f2a3b4c5")
    token_id, run_id, audit_id = (str(uuid4()) for _ in range(3))

    async def seed() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("""INSERT INTO access_tokens
                    (id, user_id, name, token_hash, scopes, active)
                    VALUES (:token, 'migration-owner', 'owner', :digest, '["manage"]', true)
                    """), {"token": token_id, "digest": "a" * 64})
                await conn.execute(text("""INSERT INTO agent_runs
                    (id, user_id, operation, request_key, request_hash, status, payload,
                     confirmation, input_epoch, attempts, max_attempts, fencing_token, event_seq)
                    VALUES (:run, 'migration-owner', 'job_analysis', 'key', :digest,
                            'running', '{}', 'approved', 0, 1, 3, 2, 0)
                    """), {"run": run_id, "digest": "b" * 64})
                insert_audit = text("""INSERT INTO audit_events
                    (id, user_id, action, resource_type, details)
                    VALUES (:audit, 'migration-owner', 'mcp.evidence.search', 'evidence', :details)
                    """).bindparams(bindparam("details", type_=JSON))
                await conn.execute(insert_audit, {
                    "audit": audit_id,
                    "details": {"count": 2, "query": "synthetic-private-search-marker"},
                })
        finally:
            await engine.dispose()

    async def validate() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(text("select version_num from alembic_version")) == (
                    _head_revision()
                )
                token = (await conn.execute(text(
                    "select audience, resource, expires_at from access_tokens where id=:id"
                ), {"id": token_id})).one()
                assert token[:2] == ("api", None)
                expires = token.expires_at
                if isinstance(expires, str):
                    expires = datetime.fromisoformat(expires)
                assert datetime.now(UTC) < expires.replace(tzinfo=UTC) <= (
                    datetime.now(UTC) + timedelta(days=7)
                )
                run = (await conn.execute(text(
                    "select status, fencing_token, event_seq from agent_runs where id=:id"
                ), {"id": run_id})).one()
                assert tuple(run) == ("interrupted", 3, 1)
                details = await conn.scalar(text(
                    "select details from audit_events where id=:id"
                ), {"id": audit_id})
                assert "synthetic-private-search-marker" not in str(details)
                assert "count" in str(details)
        finally:
            await engine.dispose()

    asyncio.run(seed())
    run_migrations(url)
    asyncio.run(validate())


def test_migration_runner_adopts_legacy_create_all_database(tmp_path):
    database_path = tmp_path / "legacy.db"
    async_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    async def create_legacy_schema() -> None:
        engine = create_async_engine(async_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(ConversationThread.__table__.drop)
            await connection.run_sync(ConversationMessage.__table__.drop)
            await connection.run_sync(AccountDeletionReceipt.__table__.drop)
            await connection.run_sync(ParsedBlock.__table__.drop)
            await connection.run_sync(SourceDocument.__table__.drop)
        await engine.dispose()

    asyncio.run(create_legacy_schema())
    run_migrations(async_url)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(text("select version_num from alembic_version"))
    assert revision == _head_revision()
    assert "conversation_threads" in inspect(engine).get_table_names()
    assert "account_deletion_receipts" in inspect(engine).get_table_names()
    engine.dispose()
