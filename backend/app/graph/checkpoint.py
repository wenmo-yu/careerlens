from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import get_settings
from app.graph.career import configure_career_graph


@asynccontextmanager
async def configure_checkpoint() -> AsyncIterator[None]:
    settings = get_settings()
    use_postgres = settings.checkpoint_backend == "postgres" or (
        settings.checkpoint_backend == "auto"
        and settings.checkpoint_url.startswith(("postgresql://", "postgres://"))
    )
    if not use_postgres:
        configure_career_graph(InMemorySaver())
        yield
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_url) as checkpointer:
        await checkpointer.setup()
        configure_career_graph(checkpointer)
        yield
