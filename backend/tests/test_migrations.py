import asyncio

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
from app.migration_runner import run_migrations
from app.models.account_deletion import AccountDeletionReceipt
from app.models.conversation import ConversationThread


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
        "audit_events",
        "career_reports",
        "conversation_threads",
        "evaluation_runs",
        "evidence",
        "job_analyses",
        "profile_items",
        "profile_update_proposals",
    } <= tables
    with engine.connect() as connection:
        revision = connection.scalar(text("select version_num from alembic_version"))
    assert revision == "c603b5469069"
    engine.dispose()


def test_migration_runner_adopts_legacy_create_all_database(tmp_path):
    database_path = tmp_path / "legacy.db"
    async_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    async def create_legacy_schema() -> None:
        engine = create_async_engine(async_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(ConversationThread.__table__.drop)
            await connection.run_sync(AccountDeletionReceipt.__table__.drop)
        await engine.dispose()

    asyncio.run(create_legacy_schema())
    run_migrations(async_url)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        revision = connection.scalar(text("select version_num from alembic_version"))
    assert revision == "c603b5469069"
    assert "conversation_threads" in inspect(engine).get_table_names()
    assert "account_deletion_receipts" in inspect(engine).get_table_names()
    engine.dispose()
