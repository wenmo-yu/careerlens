"""Agent scheduler: admission, warm pool, bind, drive and settlement (M3/M4).

One scheduler process owns agent runs. It never generates answers; it spawns a
per-session CLI, relays JSONL frames, and commits facts after validating the
attempt, runtime generation and fencing token.

Settlement path: ``run.acknowledged`` (CLI accepted) -> ``run.settled`` (CLI
finished) -> ``run.committed`` + terminal status (database authority).
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.models.agent import AgentRuntimeSlot
from app.runtime.agent import capability, store
from app.runtime.agent.pool import Pool

LOG = logging.getLogger(__name__)
PROTOCOL = 1
ALLOWED_EVENTS = {
    "message.delta",
    "message.completed",
    "tool.requested",
    "tool.completed",
    "approval.requested",
    "run.settled",
}


@dataclass
class SchedulerConfig:
    max_running: int = 2
    warm_target: int = 1
    warm_max: int = 2
    total_cap: int = 6
    warm_ttl: float = 600.0
    idle_bound_ttl: float = 300.0
    turn_timeout: float = 180.0
    bind_timeout: float = 30.0
    poll_seconds: float = 0.25
    history_limit: int = 20

    @classmethod
    def from_settings(cls) -> SchedulerConfig:
        settings = get_settings()
        return cls(
            max_running=settings.agent_max_running,
            warm_target=settings.agent_warm_target,
            warm_max=settings.agent_warm_max,
            total_cap=settings.agent_total_cap,
            warm_ttl=settings.agent_warm_ttl_seconds,
            idle_bound_ttl=settings.agent_idle_bound_seconds,
            turn_timeout=settings.agent_turn_timeout_seconds,
            bind_timeout=30.0,
            poll_seconds=settings.agent_scheduler_poll_seconds,
        )


class CliProcess:
    """One warm/bound CLI process with JSONL request/response handling."""

    def __init__(self, slot_id: str, process: asyncio.subprocess.Process):
        self.slot_id = slot_id
        self.process = process
        self.pending: deque[dict] = deque()
        self.stderr_tail: deque[str] = deque(maxlen=20)
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self._send_lock = asyncio.Lock()

    async def _drain_stderr(self) -> None:
        assert self.process.stderr is not None
        while True:
            line = await self.process.stderr.readline()
            if not line:
                return
            self.stderr_tail.append(line.decode("utf-8", "replace").rstrip()[:500])

    async def send(self, frame: dict) -> None:
        assert self.process.stdin is not None
        async with self._send_lock:
            self.process.stdin.write((json.dumps(frame, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()

    async def read_frame(self, timeout: float) -> dict:
        assert self.process.stdout is not None
        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
        if not line:
            raise EOFError("CLI closed stdout")
        return json.loads(line.decode("utf-8", "strict"))

    async def request(self, method: str, params: dict, timeout: float) -> dict:
        request_id = f"s-{uuid.uuid4().hex[:10]}"
        await self.send(
            {"v": 1, "type": "request", "id": request_id, "method": method, "params": params}
        )
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out")
            frame = await self.read_frame(remaining)
            if frame.get("type") == "event":
                self.pending.append(frame)
                continue
            if frame.get("type") == "response" and frame.get("id") == request_id:
                if not frame.get("ok"):
                    error = frame.get("error") or {}
                    raise RuntimeError(error.get("code", "cli_error"))
                return frame.get("result") or {}

    async def next_event(self, timeout: float) -> dict:
        if self.pending:
            return self.pending.popleft()
        return await self.read_frame(timeout)

    async def stop(self) -> None:
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=3)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        finally:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)


@dataclass
class DriveResult:
    outcome: str
    stop_reason: str | None = None
    error: str | None = None


class AgentScheduler:
    def __init__(
        self,
        factory: async_sessionmaker,
        *,
        owner: str | None = None,
        config: SchedulerConfig | None = None,
        cli_command: list[str] | None = None,
        api_base: str | None = None,
    ):
        self.factory = factory
        self.owner = owner or str(uuid.uuid4())
        self.config = config or SchedulerConfig.from_settings()
        self.cli_command = cli_command or [
            sys.executable,
            "-m",
            get_settings().agent_cli_module,
            "--warm",
        ]
        self.api_base = api_base or get_settings().agent_api_base
        self.pool = Pool(
            warm_target=self.config.warm_target,
            warm_max=self.config.warm_max,
            total_cap=self.config.total_cap,
            warm_ttl=self.config.warm_ttl,
            idle_bound_ttl=self.config.idle_bound_ttl,
        )
        self.processes: dict[str, CliProcess] = {}
        self.tasks: set[asyncio.Task] = set()
        self.stopping = asyncio.Event()
        self.started_at = time.time()

    # ---- lifecycle ---------------------------------------------------
    async def startup(self) -> None:
        """Reconcile slots left by a previous scheduler; they are not trusted."""

        async with self.factory.begin() as session:
            await session.execute(
                update(AgentRuntimeSlot)
                .where(AgentRuntimeSlot.state.not_in(("faulted", "terminated")))
                .values(
                    state="faulted",
                    pid=None,
                    diagnostics={"fault_reason": "scheduler_restart"},
                )
            )
        LOG.info("agent scheduler %s started", self.owner)

    async def shutdown(self) -> None:
        self.stopping.set()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for process in list(self.processes.values()):
            await process.stop()
        self.processes.clear()

    # ---- main loop ---------------------------------------------------
    async def tick(self) -> None:
        for slot in self.pool.evict_idle():
            await self._retire(slot, "evicted")
        await self._refill_warm()
        await self._reap_tasks()
        if len(self.tasks) >= self.config.max_running:
            return
        claim = None
        async with self.factory.begin() as session:
            claim = await store.claim_agent_run(
                session, owner=self.owner, max_running=self.config.max_running
            )
        if claim is None:
            return
        task = asyncio.create_task(self._drive(claim))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run_forever(self) -> None:
        await self.startup()
        while not self.stopping.is_set():
            try:
                await self.tick()
            except Exception:  # keep the scheduler alive; log with traceback
                LOG.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(
                    self.stopping.wait(), timeout=self.config.poll_seconds
                )
            except TimeoutError:
                pass

    async def _reap_tasks(self) -> None:
        for task in list(self.tasks):
            if task.done():
                self.tasks.discard(task)
                exc = task.exception()
                if exc is not None:
                    LOG.warning("agent drive failed: %s", type(exc).__name__)

    async def _refill_warm(self) -> None:
        if self.pool.warm_deficit() <= 0:
            return
        if not self.pool.can_spawn():
            return
        if time.monotonic() < self.pool.next_spawn_at:
            return
        slot = self.pool.spawn(str(uuid.uuid4()))
        try:
            await self._spawn_warm(slot)
        except Exception as exc:
            LOG.warning("warm spawn failed: %s", type(exc).__name__)
            self.pool.fault(slot, f"spawn_failed:{type(exc).__name__}")
            await self._persist_slot(slot)

    async def _spawn_warm(self, slot) -> None:
        await self._persist_slot(slot)
        process = await asyncio.create_subprocess_exec(
            *self.cli_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_cli_env(),
        )
        cli = CliProcess(slot.slot_id, process)
        self.processes[slot.slot_id] = cli
        frame = await cli.next_event(self.config.bind_timeout)
        if frame.get("kind") != "runtime.ready":
            await cli.stop()
            self.processes.pop(slot.slot_id, None)
            raise RuntimeError("CLI did not announce readiness")
        self.pool.mark_warm(slot, pid=process.pid)
        await self._persist_slot(slot)

    async def _acquire_slot(self, claim: store.AgentClaim, generation: int):
        slot = self.pool.reserve(
            session_id=claim.session_id, generation=generation, run_id=claim.run_id
        )
        if slot is None:
            if not self.pool.can_spawn():
                return None
            slot = self.pool.spawn(str(uuid.uuid4()))
            await self._spawn_warm(slot)
            slot = self.pool.reserve(
                session_id=claim.session_id, generation=generation, run_id=claim.run_id
            )
        await self._persist_slot(slot)
        return slot

    # ---- one run -----------------------------------------------------
    async def _drive(self, claim: store.AgentClaim) -> DriveResult:
        slot = None
        heartbeat: asyncio.Task | None = None
        try:
            async with self.factory.begin() as session:
                generation = await store.bind_generation(session, claim=claim)
            slot = await self._acquire_slot(claim, generation)
            if slot is None:
                await self._fail(claim, "no_capacity", retry=True)
                return DriveResult("rejected", error="no_capacity")
            cli = self.processes.get(slot.slot_id)
            if cli is None:
                self.pool.fault(slot, "process_missing")
                await self._persist_slot(slot)
                await self._fail(claim, "process_missing", retry=True)
                return DriveResult("faulted", error="process_missing")

            messages = await self._history(claim)
            token = capability.issue(
                user_id=claim.user_id,
                session_id=claim.session_id,
                run_id=claim.run_id,
                attempt=claim.attempt,
                runtime_generation=generation,
            )
            await cli.request(
                "runtime.bind",
                {
                    "session_id": claim.session_id,
                    "runtime_generation": generation,
                    "run_id": claim.run_id,
                    "attempt": claim.attempt,
                    "api_base": self.api_base,
                    "capability": token,
                    "protocol": PROTOCOL,
                    "messages": messages,
                },
                self.config.bind_timeout,
            )
            self.pool.mark_ready(slot)
            await self._persist_slot(slot)
            await cli.request(
                "run.start",
                {
                    "run_id": claim.run_id,
                    "attempt": claim.attempt,
                    "runtime_generation": generation,
                    "input": claim.text,
                },
                self.config.bind_timeout,
            )
            async with self.factory.begin() as session:
                await store.acknowledge(
                    session, claim=claim, generation=generation, slot_id=slot.slot_id
                )
            self.pool.mark_running(slot)
            await self._persist_slot(slot)

            heartbeat = asyncio.create_task(self._keep_lease(claim))
            return await self._consume(cli, claim, generation)
        except store.StaleClaim:
            if slot is not None:
                self.pool.fault(slot, "stale_generation")
                await self._persist_slot(slot)
            await self._fail(claim, "stale_generation", retry=True)
            return DriveResult("stale", error="stale_generation")
        except asyncio.CancelledError:
            await self._fail(claim, "scheduler_shutdown", retry=True)
            raise
        except (TimeoutError, EOFError, RuntimeError) as exc:
            reason = "cli_timeout" if isinstance(exc, TimeoutError) else (
                "cli_exit" if isinstance(exc, EOFError) else "cli_error"
            )
            if slot is not None:
                self.pool.fault(slot, reason)
                await self._persist_slot(slot)
            await self._fail(claim, reason, retry=True)
            return DriveResult("faulted", error=reason)
        except Exception as exc:  # durable failure must not hang the run
            LOG.exception("agent drive crashed")
            await self._fail(claim, f"internal:{type(exc).__name__}", retry=True)
            return DriveResult("failed", error=type(exc).__name__)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            if slot is not None:
                await self._retire(slot, "run_finished")

    async def _consume(self, cli: CliProcess, claim: store.AgentClaim, generation: int):
        deadline = time.monotonic() + self.config.turn_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("turn timed out")
            frame = await cli.next_event(remaining)
            if frame.get("type") != "event":
                continue
            if frame.get("run_id") not in (None, claim.run_id):
                raise RuntimeError("event for a different run")
            if int(frame.get("attempt", 0) or 0) not in (0, claim.attempt):
                raise store.StaleClaim("event from a stale attempt")
            if int(frame.get("runtime_generation", 0) or 0) not in (0, generation):
                raise store.StaleClaim("event from a stale runtime generation")
            kind = str(frame.get("kind", ""))
            payload = frame.get("payload") or {}
            if kind == "run.settled":
                message = payload.get("message") or {}
                async with self.factory.begin() as session:
                    await store.settle(
                        session,
                        claim=claim,
                        generation=generation,
                        stop_reason=str(payload.get("stop_reason", "completed")),
                        text=str(message.get("text", "")),
                        citations=list(message.get("citations") or []),
                        usage=dict(payload.get("usage") or {}),
                    )
                return DriveResult("committed", stop_reason=str(payload.get("stop_reason")))
            if kind == "approval.requested":
                async with self.factory.begin() as session:
                    await store.wait_for_approval(
                        session,
                        claim=claim,
                        generation=generation,
                        invocation_id=str(payload.get("invocation_id", "")),
                        tool=str(payload.get("tool", "")),
                        args_digest=str(payload.get("args_digest", "")),
                    )
                return DriveResult("waiting_approval")
            if kind not in ALLOWED_EVENTS:
                LOG.warning("ignoring unregistered agent event %s", kind)
                continue
            async with self.factory.begin() as session:
                await store.append_event(
                    session,
                    claim=claim,
                    generation=generation,
                    kind=kind,
                    data=payload,
                )

    async def _keep_lease(self, claim: store.AgentClaim) -> None:
        interval = max(1.0, get_settings().agent_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            async with self.factory.begin() as session:
                if not await store.heartbeat(session, claim=claim):
                    return

    async def _history(self, claim: store.AgentClaim) -> list[dict]:
        async with self.factory() as session:
            rows = await store.read_messages(
                session,
                user_id=claim.user_id,
                session_id=claim.session_id,
                after_seq=0,
                limit=self.config.history_limit,
            )
            return [
                {"role": row.role, "content": row.content}
                for row in rows
                if row.role in ("user", "assistant")
            ][-self.config.history_limit :]

    async def _fail(self, claim: store.AgentClaim, reason: str, *, retry: bool) -> None:
        try:
            async with self.factory.begin() as session:
                await store.fail_claim(session, claim=claim, reason=reason, retry=retry)
        except Exception:
            LOG.exception("failed to record run failure")

    async def _retire(self, slot, reason: str) -> None:
        if not slot.terminal:
            self.pool.drain(slot, reason)
            await self._persist_slot(slot)
        process = self.processes.pop(slot.slot_id, None)
        if process is not None:
            await process.stop()
        if not slot.terminal:
            self.pool.terminate(slot)
            await self._persist_slot(slot)

    async def _persist_slot(self, slot) -> None:
        async with self.factory.begin() as session:
            record = await session.get(AgentRuntimeSlot, slot.slot_id)
            if record is None:
                record = AgentRuntimeSlot(slot_id=slot.slot_id)
                session.add(record)
            record.state = slot.state
            record.generation = slot.generation
            record.session_id = slot.session_id
            record.run_id = slot.run_id
            record.pid = slot.pid
            record.fencing_token = slot.fencing_token
            record.restarts = slot.restarts
            record.diagnostics = dict(slot.diagnostics)
            record.state_changed_at = _now()

    async def wait_idle(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while self.tasks and time.monotonic() < deadline:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
            await asyncio.sleep(0)


def _cli_env() -> dict:
    import os

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def run_scheduler(factory: async_sessionmaker | None = None) -> None:
    from app.core.database import SessionFactory

    scheduler = AgentScheduler(factory or SessionFactory)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    runner = asyncio.create_task(scheduler.run_forever())
    stopper = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)
    await scheduler.shutdown()
    runner.cancel()
    await asyncio.gather(runner, stopper, return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
