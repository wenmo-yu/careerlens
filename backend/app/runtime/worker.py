import asyncio
import logging
import signal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import undefer

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.llm.provider import ModelUnavailable
from app.models.run import AgentRun
from app.runtime.deletion_work import process_deletion_work
from app.runtime.index_outbox import process_index_work
from app.runtime.operations import ParserUnavailable, prepare_operation
from app.runtime.store import (
    Claim,
    LeaseLost,
    RunAccessRevoked,
    StaleInput,
    check_inputs,
    claim_next,
    close_running_steps,
    end,
    event,
    heartbeat,
    interrupt,
    live_claim,
    lock_claim,
    require_run_actor,
    scope,
    step,
)
from app.services.reports import StaleJobAnalysisError
from app.services.wiki_pages import StaleWikiWriteError
from app.wiki.compiler import WikiCompileError

LOG = logging.getLogger(__name__)


async def tick(factory: async_sessionmaker, owner: str) -> Claim | None:
    async with factory.begin() as session:
        return await claim_next(session, owner)


async def keep_lease(factory: async_sessionmaker, claim: Claim) -> None:
    lease_seconds = get_settings().run_lease_seconds
    interval = min(2, lease_seconds / 3)
    loop = asyncio.get_running_loop()
    renewed = loop.time()
    while True:
        await asyncio.sleep(interval)
        try:
            async with factory.begin() as session:
                if not await heartbeat(session, claim):
                    raise LeaseLost
            renewed = loop.time()
        except SQLAlchemyError as exc:
            if loop.time() - renewed >= lease_seconds - interval:
                raise LeaseLost from exc


async def execute(factory: async_sessionmaker, claim: Claim) -> None:
    async with factory() as session:
        run = await session.scalar(
            select(AgentRun).options(undefer(AgentRun.payload), undefer(AgentRun.upload_bytes))
            .where(*live_claim(claim))
        )
        if run is None:
            raise LeaseLost
        await require_run_actor(session, claim.user_id, run.actor_token_id)
        await check_inputs(session, run)
        payload, upload = run.payload, run.upload_bytes

    async def progress(name: str, status: str, **data) -> None:
        async with factory.begin() as session:
            run = await lock_claim(session, claim)
            await step(session, run, name, status)
            await event(session, run, f"step.{status}", step=name, **data)

    effect = await prepare_operation(
        factory, operation=claim.operation, user_id=claim.user_id,
        data=payload, upload=upload, progress=progress,
    )
    async with factory.begin() as session:
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        primary_epoch = await scope(session, claim.user_id)
        run = await lock_claim(session, claim)
        await require_run_actor(session, claim.user_id, run.actor_token_id)
        await check_inputs(session, run, lock=True, primary=primary_epoch)
        result = await effect(session)
        await step(session, run, "persist", "succeeded")
        await event(session, run, "step.succeeded", step="persist")
        await end(session, run, "succeeded", result=result)


async def settle_error(
    factory: async_sessionmaker, claim: Claim, reason: str, *, retry: bool = False
) -> None:
    try:
        async with factory.begin() as session:
            run = await lock_claim(session, claim)
            if retry:
                await interrupt(session, run, reason)
            else:
                await close_running_steps(session, run, "failed")
                await end(session, run, "failed", reason=reason)
    except LeaseLost:
        return


async def perform(factory: async_sessionmaker, claim: Claim) -> None:
    work = asyncio.create_task(execute(factory, claim))
    guard = asyncio.create_task(keep_lease(factory, claim))
    try:
        async with asyncio.timeout(get_settings().run_timeout_seconds):
            done, _ = await asyncio.wait({work, guard}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                await work
            else:
                await guard
    except LeaseLost:
        return
    except asyncio.CancelledError:
        work.cancel()
        guard.cancel()
        await asyncio.gather(work, guard, return_exceptions=True)
        await settle_error(factory, claim, "worker_shutdown", retry=True)
        raise
    except Exception as exc:
        work.cancel()
        guard.cancel()
        await asyncio.gather(work, guard, return_exceptions=True)
        if isinstance(exc, (StaleInput, StaleJobAnalysisError, StaleWikiWriteError)):
            reason = "stale_input"
        elif isinstance(exc, RunAccessRevoked):
            reason = "permission_revoked"
        elif isinstance(exc, ParserUnavailable):
            reason = "parser_unavailable"
        elif isinstance(exc, ModelUnavailable):
            reason = "model_unavailable"
        elif isinstance(exc, (ValueError, WikiCompileError)):
            reason = "invalid_input"
        elif isinstance(exc, TimeoutError):
            reason = "timeout"
        else:
            reason = "worker_error"
            LOG.warning("Run %s failed with %s", claim.run_id, type(exc).__name__)
        retry = reason in {"timeout", "worker_error"} or (
            isinstance(exc, ModelUnavailable)
            and exc.reason in {"connection_error", "timeout", "rate_limit", "upstream_error"}
        )
        await settle_error(factory, claim, reason, retry=retry)
    finally:
        work.cancel()
        guard.cancel()
        await asyncio.gather(work, guard, return_exceptions=True)


async def worker_loop(
    factory: async_sessionmaker, owner: str, stop: asyncio.Event, *, indexing: bool = False
) -> None:
    while not stop.is_set():
        try:
            if indexing:
                deletion_handled = await process_deletion_work(factory)
                async with factory.begin() as session:
                    handled = await process_index_work(session)
                if deletion_handled or handled:
                    continue
            else:
                claim = await tick(factory, owner)
                if claim is not None:
                    await perform(factory, claim)
                    continue
        except Exception as exc:
            LOG.warning("Worker iteration failed with %s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except TimeoutError:
            pass


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    get_settings().validate_security("worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    owner = str(uuid4())
    workers = [
        asyncio.create_task(worker_loop(SessionFactory, owner, stop))
        for _ in range(get_settings().run_worker_concurrency)
    ]
    workers.append(asyncio.create_task(worker_loop(SessionFactory, owner, stop, indexing=True)))
    try:
        await stop.wait()
    finally:
        _, pending = await asyncio.wait(workers, timeout=5)
        for task in pending:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
