import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base, build_engine

LEGACY_TABLES = {
    "access_tokens",
    "audit_events",
    "career_reports",
    "evaluation_runs",
    "evidence",
    "job_analyses",
    "profile_items",
    "profile_update_proposals",
}


async def _prepare_legacy_database(database_url: str) -> bool:
    engine = build_engine(database_url)
    async with engine.begin() as connection:
        tables = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        if "alembic_version" in tables or not tables:
            legacy = False
        elif LEGACY_TABLES <= tables:
            # One-time adoption for databases created by pre-Alembic CareerLens releases.
            await connection.run_sync(Base.metadata.create_all)
            legacy = True
        else:
            unexpected = ", ".join(sorted(tables))
            raise RuntimeError(
                "Database is unversioned and does not match the legacy CareerLens schema: "
                f"{unexpected}"
            )
    await engine.dispose()
    return legacy


def run_migrations(database_url: str | None = None) -> None:
    selected_url = database_url or get_settings().database_url
    adopted_legacy = asyncio.run(_prepare_legacy_database(selected_url))
    config_path = Path(__file__).parents[1] / "alembic.ini"
    alembic_config = Config(str(config_path))
    alembic_config.attributes["database_url"] = selected_url
    if adopted_legacy:
        command.stamp(alembic_config, "head")
    else:
        command.upgrade(alembic_config, "head")


if __name__ == "__main__":
    run_migrations()
