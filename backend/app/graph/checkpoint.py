import asyncio

from app.core.config import get_settings


async def delete_postgres_checkpoint(thread_id: str) -> None:
    settings = get_settings()
    if not settings.uses_postgres_checkpoint:
        raise RuntimeError("Postgres checkpoint cleanup requires the configured checkpoint store")
    await asyncio.to_thread(_delete_thread, settings.checkpoint_url, thread_id)


def _delete_thread(url: str, thread_id: str) -> None:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.conninfo import make_conninfo

    # A blocking client in a bounded worker handles Windows Proactor loops too.
    conninfo = make_conninfo(url, connect_timeout=5, options="-c statement_timeout=8000")
    with PostgresSaver.from_conn_string(conninfo) as checkpointer:
        with checkpointer.conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('checkpoints') AS checkpoints")
            row = cursor.fetchone()
        if row and row["checkpoints"]:
            with checkpointer.conn.transaction():
                checkpointer.delete_thread(thread_id)
