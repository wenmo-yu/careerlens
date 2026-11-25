import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.access_token import AccessToken
from app.models.run import TERMINAL, AgentRun, RunEvent, RunScope, RunStep

INPUT = "input"
DELETION = "deletion"
ACTIVE_QUEUE = ("queued", "interrupted")


class RunConflict(ValueError):
    pass


class RunQuota(ValueError):
    pass


class LeaseLost(Exception):
    pass


class RunAccessRevoked(Exception):
    pass


class StaleInput(ValueError):
    pass


@dataclass(frozen=True)
class Claim:
    run_id: str
    user_id: str
    owner: str
    token: int
    operation: str


def now_seconds() -> int:
    return int(datetime.now(UTC).timestamp())


def dialect_insert(session: AsyncSession, model):
    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgres_insert
    return insert(model)


async def check_inputs(
    session: AsyncSession, run: AgentRun, *, lock: bool = False, primary: int | None = None
) -> None:
    async def generation(key: str) -> int:
        if lock:
            return await scope(session, run.user_id, key)
        return (await session.scalar(
            select(RunScope.generation).where(RunScope.user_id == run.user_id, RunScope.key == key)
        )) or 0

    key = DELETION if run.operation in {"file_import", "media_import"} else INPUT
    epoch = primary if key == INPUT and primary is not None else await generation(key)
    if run.input_epoch != epoch:
        raise StaleInput
    if run.target_key and run.target_generation != await generation(run.target_key):
        raise StaleInput


async def require_run_actor(session: AsyncSession, user_id: str, token_id: str | None) -> None:
    if token_id is None:
        if get_settings().auth_mode.lower() != "required":
            return
    else:
        token = await session.scalar(
            select(AccessToken).where(
                AccessToken.id == token_id, AccessToken.user_id == user_id,
                AccessToken.active.is_(True),
            )
        )
        if token is not None and set(token.scopes).intersection({"write", "manage"}):
            return
    raise RunAccessRevoked


async def scope(
    session: AsyncSession, user_id: str, key: str = INPUT, *, bump: bool = False
) -> int:
    await session.execute(
        dialect_insert(session, RunScope)
        .values(user_id=user_id, key=key, generation=0)
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
    )
    return await session.scalar(
        update(RunScope)
        .where(RunScope.user_id == user_id, RunScope.key == key)
        .values(generation=RunScope.generation + int(bump))
        .returning(RunScope.generation)
    )


async def event(session: AsyncSession, run: AgentRun, kind: str, **data: Any) -> None:
    """Append an event with a database-assigned, race-free sequence number.

    HY4-E: the old ``run.event_seq += 1`` happened in Python on an ORM object.
    With parallel specialists each progress callback opens its own transaction,
    so two callbacks could read the same seq and write duplicate RunEvent rows.
    ``UPDATE ... RETURNING`` makes the database assign the next number inside a
    row lock, so concurrent writers always get distinct, consecutive values.
    """
    seq = await session.scalar(
        update(AgentRun)
        .where(AgentRun.id == run.id)
        .values(event_seq=AgentRun.event_seq + 1)
        .returning(AgentRun.event_seq)
    )
    if seq is None:
        raise RunConflict("Run no longer exists")
    run.event_seq = seq
    session.add(
        RunEvent(
            run_id=run.id, user_id=run.user_id, seq=seq,
            generation=run.fencing_token, event_type=kind, data=data,
        )
    )


async def step(session: AsyncSession, run: AgentRun, name: str, status: str) -> None:
    values = {"status": status, "attempt": run.attempts, "updated_at": datetime.now(UTC)}
    await session.execute(
        dialect_insert(session, RunStep)
        .values(run_id=run.id, user_id=run.user_id, name=name, **values)
        .on_conflict_do_update(index_elements=["run_id", "name"], set_=values)
    )


async def submit(
    session: AsyncSession,
    *,
    user_id: str,
    token_id: str | None,
    request_key: str,
    operation: str,
    payload: dict,
    confirmation: bool,
    upload: bytes | None = None,
    target: str | None = None,
) -> tuple[AgentRun, bool]:
    input_epoch = await scope(session, user_id)
    await require_run_actor(session, user_id, token_id)
    digest = hashlib.sha256(
        json.dumps(
            [operation, confirmation, payload], sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    existing = await session.scalar(
        select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_key == request_key)
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise RunConflict("Idempotency-Key was already used with different input")
        return existing, False
    pending = await session.scalar(
        select(func.count()).select_from(AgentRun)
        .where(AgentRun.user_id == user_id, AgentRun.status.not_in(TERMINAL))
    )
    if pending >= get_settings().run_pending_per_user:
        raise RunQuota("Too many active runs for this user")
    if operation in {"file_import", "media_import"}:
        input_epoch = await scope(session, user_id, DELETION)

    generation = await scope(session, user_id, target, bump=not confirmation) if target else None
    run = AgentRun(
        user_id=user_id, actor_token_id=token_id, request_key=request_key, request_hash=digest,
        payload=payload, upload_bytes=upload, operation=operation,
        status="waiting_confirmation" if confirmation else "queued",
        confirmation="pending" if confirmation else "none",
        input_epoch=input_epoch, target_key=target, target_generation=generation,
    )
    session.add(run)
    await session.flush()
    await event(session, run, "run.waiting_confirmation" if confirmation else "run.queued")
    return run, True


async def get_run(
    session: AsyncSession, user_id: str, run_id: str, *, lock: bool = False
) -> AgentRun | None:
    criteria = (AgentRun.id == run_id, AgentRun.user_id == user_id)
    if lock:
        locked = await session.scalar(
            update(AgentRun).where(*criteria).values(event_seq=AgentRun.event_seq)
            .returning(AgentRun.id)
        )
        if locked is None:
            return None
    return await session.scalar(
        select(AgentRun).where(*criteria).execution_options(populate_existing=True)
    )


async def end(
    session: AsyncSession,
    run: AgentRun,
    status: str,
    *,
    result: dict | None = None,
    reason: str | None = None,
) -> None:
    run.status = status
    run.result = result
    run.error_code = reason
    run.lease_owner = None
    run.lease_until = None
    run.upload_bytes = None
    run.payload = {}
    await event(session, run, f"run.{status}", **({"reason": reason} if reason else {}))


async def decide(session: AsyncSession, user_id: str, run_id: str, approve: bool):
    await scope(session, user_id)
    run = await get_run(session, user_id, run_id, lock=True)
    if run is None:
        return None
    decision = "approved" if approve else "rejected"
    if run.confirmation == decision:
        return run
    if run.status != "waiting_confirmation":
        raise RunConflict("Run is not waiting for confirmation")
    run.confirmation = decision
    if approve:
        if run.target_key:
            run.target_generation = await scope(session, user_id, run.target_key, bump=True)
        run.status = "queued"
        await event(session, run, "run.approved")
    else:
        await end(session, run, "cancelled", reason="rejected")
    return run


async def cancel(session: AsyncSession, user_id: str, run_id: str):
    run = await get_run(session, user_id, run_id, lock=True)
    if run is not None and run.status not in TERMINAL:
        await close_running_steps(session, run, "cancelled")
        run.fencing_token += 1
        await end(session, run, "cancelled", reason="cancelled_by_user")
    return run


async def close_running_steps(session: AsyncSession, run: AgentRun, status: str) -> None:
    await session.execute(
        update(RunStep).where(RunStep.run_id == run.id, RunStep.status == "running")
        .values(status=status, updated_at=datetime.now(UTC))
    )


async def claim_next(session: AsyncSession, owner: str) -> Claim | None:
    settings = get_settings()
    await scope(session, "", "dispatcher")
    now = now_seconds()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.run_pending_hours)
    abandoned = list(await session.scalars(
        select(AgentRun)
        .where(
            AgentRun.status.in_((*ACTIVE_QUEUE, "waiting_confirmation")),
            AgentRun.created_at <= cutoff,
        )
        .order_by(AgentRun.created_at)
        .limit(16)
        .with_for_update(skip_locked=True)
    ))
    for run in abandoned:
        await end(session, run, "failed", reason="run_expired")
    expired = list(await session.scalars(
        select(AgentRun)
        .where(AgentRun.status == "running", AgentRun.lease_until <= now)
        .order_by(AgentRun.lease_until)
        .limit(settings.run_global_concurrency)
        .with_for_update(skip_locked=True)
    ))
    for run in expired:
        await interrupt(session, run, "lease_expired")
    await session.flush()

    active_query = select(AgentRun.user_id).where(AgentRun.status == "running")
    active_users = set(await session.scalars(active_query))
    if len(active_users) >= settings.run_global_concurrency:
        return None
    query = select(AgentRun).where(AgentRun.status.in_(ACTIVE_QUEUE))
    if active_users:
        query = query.where(AgentRun.user_id.not_in(active_users))
    run = await session.scalar(
        query.order_by(AgentRun.created_at, AgentRun.id).limit(1).with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run.status = "running"
    run.fencing_token += 1
    run.attempts += 1
    run.lease_owner = owner
    run.lease_until = now_seconds() + settings.run_lease_seconds
    await event(session, run, "run.started", attempt=run.attempts)
    return Claim(run.id, run.user_id, owner, run.fencing_token, run.operation)


async def interrupt(session: AsyncSession, run: AgentRun, reason: str) -> None:
    await close_running_steps(session, run, "interrupted")
    run.fencing_token += 1
    if run.attempts >= run.max_attempts:
        await end(session, run, "failed", reason="retries_exhausted")
    else:
        run.status = "interrupted"
        run.lease_owner = None
        run.lease_until = None
        await event(session, run, "run.interrupted", reason=reason)


def live_claim(claim: Claim):
    return (
        AgentRun.id == claim.run_id,
        AgentRun.user_id == claim.user_id,
        AgentRun.status == "running",
        AgentRun.lease_owner == claim.owner,
        AgentRun.fencing_token == claim.token,
        AgentRun.lease_until > now_seconds(),
    )


async def heartbeat(session: AsyncSession, claim: Claim) -> bool:
    return (await session.scalar(
        update(AgentRun).where(*live_claim(claim))
        .values(lease_until=now_seconds() + get_settings().run_lease_seconds)
        .returning(AgentRun.id)
    )) is not None


async def lock_claim(session: AsyncSession, claim: Claim) -> AgentRun:
    found = await session.scalar(
        update(AgentRun).where(*live_claim(claim)).values(event_seq=AgentRun.event_seq)
        .returning(AgentRun.id)
    )
    if found is None:
        raise LeaseLost
    run = await session.get(AgentRun, found, populate_existing=True)
    if run is None:
        raise LeaseLost
    return run
