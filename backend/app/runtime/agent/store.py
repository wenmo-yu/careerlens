"""Durable agent-plane storage.

The rules this module enforces:

* a run is claimed with a fencing token; every later write must present it;
* ``acknowledged``, ``settled`` and ``committed`` are separate events and
  separate stages, so a crashed CLI cannot look successful;
* event ``seq`` is allocated inside the same transaction as the event row;
* a bound runtime generation is immutable for that run; a stale generation is
  rejected instead of overwriting newer facts;
* session history is append-only and ordered by ``message_seq``.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import get_settings
from app.models.agent import AgentApproval, AgentMessage, AgentSession
from app.models.run import TERMINAL, AgentRun, RunEvent
from app.runtime.store import ACTIVE_QUEUE, now_seconds, require_run_actor

# Must stay in sync with contracts/agent-runtime-v1.json (asserted in tests).
RUN_EVENT_KINDS = (
    "run.queued",
    "run.started",
    "run.acknowledged",
    "message.delta",
    "message.completed",
    "tool.requested",
    "tool.completed",
    "approval.requested",
    "approval.resolved",
    "run.settled",
    "run.committed",
    "run.interrupted",
    "run.failed",
    "run.cancelled",
)


class AgentConflict(ValueError):
    """The request contradicts durable state (wrong session, duplicate, closed)."""


class StaleClaim(Exception):
    """The claim's fencing token or runtime generation is no longer current."""


@dataclass(frozen=True)
class AgentClaim:
    run_id: str
    user_id: str
    session_id: str
    owner: str
    attempt: int
    fencing_token: int
    text: str
    # Durable recovery state (pending approval/tool) survives CLI and daemon
    # restarts; a claim without one simply carries an empty dict.
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AgentEvent:
    seq: int
    kind: str
    data: dict


async def create_session(
    session: AsyncSession, *, user_id: str, title: str = "", workspace_id: str = "default"
) -> AgentSession:
    record = AgentSession(user_id=user_id, title=title[:200], workspace_id=workspace_id[:36])
    session.add(record)
    await session.flush()
    return record


async def get_session(
    session: AsyncSession, user_id: str, session_id: str, *, lock: bool = False
) -> AgentSession | None:
    query = select(AgentSession).where(
        AgentSession.id == session_id, AgentSession.user_id == user_id
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def list_sessions(
    session: AsyncSession, user_id: str, *, limit: int = 50
) -> list[AgentSession]:
    return list(
        await session.scalars(
            select(AgentSession)
            .where(AgentSession.user_id == user_id)
            .order_by(AgentSession.updated_at.desc())
            .limit(limit)
        )
    )


async def _next_message_seq(session: AsyncSession, record: AgentSession) -> int:
    result = await session.execute(
        update(AgentSession)
        .where(AgentSession.id == record.id)
        .values(head_revision=AgentSession.head_revision + 1, updated_at=func.now())
    )
    if result.rowcount != 1:
        raise AgentConflict("Session disappeared while appending a message")
    await session.refresh(record, ["head_revision"])
    return record.head_revision


async def append_message(
    session: AsyncSession,
    *,
    record: AgentSession,
    role: str,
    content: str,
    run_id: str | None = None,
    citations: list | None = None,
) -> AgentMessage:
    seq = await _next_message_seq(session, record)
    message = AgentMessage(
        session_id=record.id,
        user_id=record.user_id,
        run_id=run_id,
        role=role,
        content=content,
        citations=citations or [],
        message_seq=seq,
    )
    session.add(message)
    await session.flush()
    return message


async def read_messages(
    session: AsyncSession, *, user_id: str, session_id: str, after_seq: int = 0, limit: int = 100
) -> list[AgentMessage]:
    return list(
        await session.scalars(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.user_id == user_id,
                AgentMessage.message_seq > after_seq,
            )
            .order_by(AgentMessage.message_seq)
            .limit(limit)
        )
    )


async def submit_turn(
    session: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    text: str,
    token_id: str | None,
    request_key: str,
) -> tuple[AgentRun, bool]:
    """Persist a user message and an idempotent agent run in one transaction."""

    record = await get_session(session, user_id, session_id, lock=True)
    if record is None:
        raise AgentConflict("Session not found")
    if record.status != "active":
        raise AgentConflict("Session is closed")
    await require_run_actor(session, user_id, token_id)

    import hashlib
    import json

    digest = hashlib.sha256(
        json.dumps(["agent_turn", session_id, text], sort_keys=True).encode()
    ).hexdigest()
    existing = await session.scalar(
        select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_key == request_key)
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise AgentConflict("Idempotency-Key was already used with different input")
        return existing, False
    pending = await session.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.user_id == user_id,
            AgentRun.executor_kind == "agent",
            AgentRun.status.not_in(TERMINAL),
        )
    )
    if pending >= get_settings().agent_pending_per_user:
        raise AgentConflict("Too many active agent runs for this user")

    await append_message(
        session, record=record, role="user", content=text, run_id=None
    )
    run = AgentRun(
        user_id=user_id,
        actor_token_id=token_id,
        request_key=request_key,
        request_hash=digest,
        payload={"session_id": session_id, "text": text},
        operation="agent_turn",
        executor_kind="agent",
        session_id=session_id,
        status="queued",
        confirmation="none",
    )
    session.add(run)
    await session.flush()
    await _append(session, run, None, "run.queued", {"session_id": session_id, "attempt": 0})
    return run, True


async def _append(
    session: AsyncSession,
    run: AgentRun,
    claim: AgentClaim | None,
    kind: str,
    data: dict[str, Any],
    *,
    generation: int | None = None,
) -> int:
    """Allocate seq and write the event; rejects stale claims atomically."""

    conditions = [AgentRun.id == run.id, AgentRun.status.not_in(TERMINAL)]
    if claim is not None:
        conditions.append(AgentRun.fencing_token == claim.fencing_token)
    result = await session.execute(
        update(AgentRun).where(*conditions).values(event_seq=AgentRun.event_seq + 1)
    )
    if result.rowcount != 1:
        raise StaleClaim("Run moved to another attempt or reached a terminal state")
    await session.refresh(run, ["event_seq", "status", "fencing_token"])
    body = dict(data)
    body.setdefault("attempt", claim.attempt if claim else 0)
    if generation is not None:
        body["runtime_generation"] = generation
    event = RunEvent(
        run_id=run.id,
        seq=run.event_seq,
        user_id=run.user_id,
        generation=generation or (claim.attempt if claim else 0),
        event_type=kind,
        data=body,
    )
    session.add(event)
    await session.flush()
    return run.event_seq


async def claim_agent_run(
    session: AsyncSession, *, owner: str, max_running: int
) -> AgentClaim | None:
    """CAS-claim one queued agent run, respecting admission and session exclusivity."""

    now = now_seconds()
    expired = list(
        await session.scalars(
            select(AgentRun)
            .where(
                AgentRun.executor_kind == "agent",
                AgentRun.status == "running",
                (AgentRun.lease_until.is_(None)) | (AgentRun.lease_until <= now),
            )
            .order_by(AgentRun.lease_until)
            .limit(max_running)
            .with_for_update(skip_locked=True)
        )
    )
    for run in expired:
        run.fencing_token += 1
        run.status = "interrupted"
        run.lease_owner = None
        run.lease_until = None
        run.error_code = "lease_expired"
        await _append(session, run, None, "run.interrupted", {"reason": "lease_expired"})
    if expired:
        await session.flush()

    active = list(
        await session.scalars(
            select(AgentRun.session_id).where(
                AgentRun.executor_kind == "agent", AgentRun.status == "running"
            )
        )
    )
    if len(active) >= max_running:
        return None
    busy_sessions = {value for value in active if value}

    query = (
        select(AgentRun)
        .options(undefer(AgentRun.payload))
        .where(AgentRun.executor_kind == "agent", AgentRun.status.in_(ACTIVE_QUEUE))
    )
    if busy_sessions:
        query = query.where(AgentRun.session_id.not_in(busy_sessions))
    run = await session.scalar(
        query.order_by(AgentRun.created_at, AgentRun.id).limit(1).with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    if not run.session_id:
        raise AgentConflict("Agent run has no session")
    run.status = "running"
    run.fencing_token += 1
    run.attempts += 1
    run.lease_owner = owner
    run.lease_until = now + get_settings().agent_lease_seconds
    payload = run.payload or {}
    run.payload = payload
    await _append(
        session,
        run,
        None,
        "run.started",
        {"attempt": run.attempts, "session_id": run.session_id},
    )
    return AgentClaim(
        run_id=run.id,
        user_id=run.user_id,
        session_id=run.session_id,
        owner=owner,
        attempt=run.attempts,
        fencing_token=run.fencing_token,
        text=str(payload.get("text", "")),
        payload=dict(payload),
    )


async def bind_generation(
    session: AsyncSession, *, claim: AgentClaim
) -> int:
    """Atomically bump and return the session runtime generation for this bind."""

    record = await get_session(session, claim.user_id, claim.session_id, lock=True)
    if record is None or record.status != "active":
        raise AgentConflict("Session is not bindable")
    record.runtime_generation += 1
    await session.flush()
    return record.runtime_generation


async def _lock_claim(session: AsyncSession, claim: AgentClaim) -> AgentRun:
    run = await session.scalar(
        select(AgentRun)
        .options(undefer(AgentRun.payload))
        .where(
            AgentRun.id == claim.run_id,
            AgentRun.fencing_token == claim.fencing_token,
            AgentRun.status.in_(("running", "waiting_confirmation")),
        )
        .with_for_update()
    )
    if run is None:
        raise StaleClaim("Claim is no longer current")
    return run


async def acknowledge(
    session: AsyncSession, *, claim: AgentClaim, generation: int, slot_id: str
) -> int:
    """Record ACK: the CLI accepted the run. This is not success."""

    run = await _lock_claim(session, claim)
    run.result = {
        "acknowledged": {
            "attempt": claim.attempt,
            "runtime_generation": generation,
            "slot_id": slot_id,
        }
    }
    return await _append(
        session,
        run,
        claim,
        "run.acknowledged",
        {"attempt": claim.attempt, "slot_id": slot_id},
        generation=generation,
    )


async def append_event(
    session: AsyncSession,
    *,
    claim: AgentClaim,
    generation: int,
    kind: str,
    data: dict[str, Any],
) -> int:
    run = await _lock_claim(session, claim)
    if generation != (run.result or {}).get("acknowledged", {}).get("runtime_generation"):
        raise StaleClaim("runtime_generation does not match the acknowledged bind")
    return await _append(session, run, claim, kind, data, generation=generation)


async def settle(
    session: AsyncSession,
    *,
    claim: AgentClaim,
    generation: int,
    stop_reason: str,
    text: str,
    citations: list | None = None,
    usage: dict | None = None,
) -> AgentRun:
    """Persist settled + committed and only then move the run to terminal."""

    run = await _lock_claim(session, claim)
    acknowledged = (run.result or {}).get("acknowledged", {})
    if generation != acknowledged.get("runtime_generation"):
        raise StaleClaim("Cannot settle a run from a stale runtime generation")
    await _append(
        session,
        run,
        claim,
        "run.settled",
        {"stop_reason": stop_reason, "usage": usage or {}},
        generation=generation,
    )
    record = await get_session(session, claim.user_id, claim.session_id, lock=True)
    if record is not None and text:
        await append_message(
            session,
            record=record,
            role="assistant",
            content=text,
            run_id=run.id,
            citations=citations or [],
        )
    await _append(
        session,
        run,
        claim,
        "run.committed",
        {"stop_reason": stop_reason, "message_chars": len(text)},
        generation=generation,
    )
    run.status = "succeeded" if stop_reason == "completed" else "failed"
    run.error_code = None if stop_reason == "completed" else stop_reason
    run.result = {
        "acknowledged": acknowledged,
        "message": text,
        "citations": citations or [],
        "usage": usage or {},
        "stop_reason": stop_reason,
    }
    run.lease_owner = None
    run.lease_until = None
    run.payload = {}
    await session.flush()
    return run


async def wait_for_approval(
    session: AsyncSession,
    *,
    claim: AgentClaim,
    generation: int,
    invocation_id: str,
    tool: str,
    args_digest: str,
    scope: str = "",
    pending_turn: dict | None = None,
    pending_tool: dict | None = None,
) -> AgentApproval:
    run = await _lock_claim(session, claim)
    approval = await session.scalar(
        select(AgentApproval).where(
            AgentApproval.run_id == run.id, AgentApproval.invocation_id == invocation_id
        )
    )
    if approval is not None and approval.args_digest != args_digest:
        raise AgentConflict(
            "Approval already exists for this invocation with a different digest"
        )
    if approval is None:
        approval = AgentApproval(
            run_id=run.id,
            user_id=run.user_id,
            session_id=run.session_id,
            invocation_id=invocation_id,
            tool=tool,
            args_digest=args_digest,
            scope=scope[:100],
        )
        session.add(approval)
        await session.flush()

    # Persist the barrier itself, not just a flag: a restarted CLI or daemon
    # must be able to replay exactly one invocation after approval.
    previous = dict(run.payload or {})
    was_waiting = (
        run.status == "waiting_confirmation"
        and str(previous.get("pending_turn", {}).get("invocation_id", "")) == invocation_id
        and previous.get("approval_requested") == approval.id
    )
    stored = dict(previous)
    if pending_turn is not None:
        stored["pending_turn"] = dict(pending_turn)
    if pending_tool is not None:
        tool_state = dict(pending_tool)
        tool_state["approval_id"] = approval.id
        stored["pending_tool"] = tool_state
    stored["approval_requested"] = approval.id
    run.payload = stored
    run.confirmation = "pending"
    run.status = "waiting_confirmation"
    run.lease_owner = None
    run.lease_until = None
    if not was_waiting:
        await _append(
            session,
            run,
            claim,
            "approval.requested",
            {
                "approval_id": approval.id,
                "invocation_id": invocation_id,
                "args_digest": args_digest,
                "tool": tool,
                "scope": scope,
            },
            generation=generation,
        )
    await session.flush()
    return approval


async def decide_approval(
    session: AsyncSession, *, user_id: str, run_id: str, approve: bool
) -> AgentRun | None:
    run = await session.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id).with_for_update()
    )
    if run is None:
        return None
    approval = await session.scalar(
        select(AgentApproval)
        .where(
            AgentApproval.run_id == run_id,
            AgentApproval.user_id == user_id,
            AgentApproval.status == "pending",
        )
        .order_by(AgentApproval.created_at.desc(), AgentApproval.id.desc())
    )
    if approval is None:
        # 重复决策结果一致时幂等返回；结果冲突则是持久冲突（409），
        # 不重复写事件，也不产生第二次副作用。
        decided = await session.scalar(
            select(AgentApproval)
            .where(AgentApproval.run_id == run_id, AgentApproval.user_id == user_id)
            .order_by(AgentApproval.created_at.desc(), AgentApproval.id.desc())
        )
        expected = "approved" if approve else "denied"
        if decided is not None and decided.status == expected:
            return run
        if decided is not None and decided.status in ("approved", "denied", "expired"):
            raise AgentConflict("Approval was already decided with a different outcome")
        raise AgentConflict("No pending approval for this run")
    if run.status != "waiting_confirmation":
        raise AgentConflict("Run is not waiting for approval")
    approval.status = "approved" if approve else "denied"
    approval.decision_by = user_id
    approval.decided_at = datetime.now(UTC)
    run.confirmation = approval.status
    if approve:
        run.status = "queued"
        run.error_code = None
        await _append(
            session, run, None, "approval.resolved", {"approval_id": approval.id, "approved": True}
        )
    else:
        await _append(
            session, run, None, "approval.resolved", {"approval_id": approval.id, "approved": False}
        )
        await _append(session, run, None, "run.cancelled", {"reason": "rejected"})
        run.status = "cancelled"
        run.error_code = "rejected"
        run.lease_owner = None
        run.lease_until = None
    await session.flush()
    return run


async def fail_claim(
    session: AsyncSession, *, claim: AgentClaim, reason: str, retry: bool
) -> None:
    try:
        run = await _lock_claim(session, claim)
    except StaleClaim:
        return
    run.fencing_token += 1
    if retry and run.attempts < run.max_attempts:
        run.status = "interrupted"
        run.error_code = reason
        run.lease_owner = None
        run.lease_until = None
        await _append(session, run, None, "run.interrupted", {"reason": reason})
    else:
        await _append(session, run, None, "run.failed", {"reason": reason})
        run.status = "failed"
        run.error_code = reason
        run.lease_owner = None
        run.lease_until = None
        run.payload = {}


async def heartbeat(session: AsyncSession, *, claim: AgentClaim) -> bool:
    result = await session.execute(
        update(AgentRun)
        .where(
            AgentRun.id == claim.run_id,
            AgentRun.fencing_token == claim.fencing_token,
            AgentRun.status == "running",
        )
        .values(lease_until=now_seconds() + get_settings().agent_lease_seconds)
    )
    return result.rowcount == 1


async def pending_approvals(
    session: AsyncSession, *, user_id: str, limit: int = 50
) -> list[AgentApproval]:
    return list(
        await session.scalars(
            select(AgentApproval)
            .where(AgentApproval.user_id == user_id, AgentApproval.status == "pending")
            .order_by(AgentApproval.created_at)
            .limit(limit)
        )
    )


def lease_deadline(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)
