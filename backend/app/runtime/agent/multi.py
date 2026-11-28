"""Durable multi-agent task trees and team mailbox (M6).

Guiding rules:

* each child task owns a separate agent session, so histories are isolated;
* the parent receives only a bounded result projection with verified citations;
* team mail is deduplicated by ``(team_id, message_key)``;
* cancelling a parent cancels the whole subtree, including queued runs;
* budget is cumulative across attempts and is never reset by a restart.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.multi import (
    TERMINAL_TASK_STATES,
    AgentTask,
    AgentTaskBudgetUse,
    AgentTeamMessage,
)
from app.models.run import TERMINAL as TERMINAL_RUN_STATES
from app.models.run import AgentRun
from app.runtime.agent import store

ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "researcher": ("search_evidence", "get_profile"),
    "reviewer": ("search_evidence", "get_profile"),
    "synthesizer": ("search_evidence", "get_profile"),
}
DEFAULT_ROLES = ("researcher", "reviewer", "synthesizer")
MAX_CHILDREN = 3
MAX_PROJECTION_CHARS = 2000


class MultiAgentConflict(ValueError):
    """The requested task tree contradicts durable state."""


def _digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


async def _budget_use(session: AsyncSession, task_id: str) -> AgentTaskBudgetUse:
    record = await session.get(AgentTaskBudgetUse, task_id)
    if record is None:
        record = AgentTaskBudgetUse(task_id=task_id)
        session.add(record)
        await session.flush()
    return record


async def create_team(
    session: AsyncSession,
    *,
    user_id: str,
    workspace_id: str,
    title: str,
    inputs: list[dict[str, Any]],
    token_id: str | None,
    budget: dict[str, Any] | None = None,
) -> tuple[AgentTask, list[AgentTask]]:
    """Create one parent and up to three role-scoped child runs.

    Each child gets its own session and run. The parent task is a coordinator
    row only; it never executes a model turn itself.
    """

    if not title.strip() or len(title) > 200:
        raise MultiAgentConflict("title must contain 1-200 characters")
    if not 1 <= len(inputs) <= MAX_CHILDREN:
        raise MultiAgentConflict(f"a team needs 1-{MAX_CHILDREN} child inputs")
    roles = [str(item.get("role", "")).strip() for item in inputs]
    if len(set(roles)) != len(roles) or any(role not in ROLE_SCOPES for role in roles):
        raise MultiAgentConflict("child roles must be unique and registered")
    team_id = str(uuid.uuid4())
    parent = AgentTask(
        user_id=user_id,
        workspace_id=workspace_id,
        team_id=team_id,
        role="coordinator",
        title=title[:200],
        input=title[:200],
        status="waiting",
        budget={"max_children": MAX_CHILDREN, **(budget or {})},
    )
    session.add(parent)
    await session.flush()

    children: list[AgentTask] = []
    for item in inputs:
        role = str(item["role"])
        text = str(item.get("input", "")).strip()
        if not text or len(text) > 20_000:
            raise MultiAgentConflict(f"{role} input must contain 1-20000 characters")
        child_session = await store.create_session(
            session, user_id=user_id, title=f"{title[:80]} / {role}", workspace_id=workspace_id
        )
        request_key = f"team:{team_id}:{role}"
        run, _created = await store.submit_turn(
            session,
            user_id=user_id,
            session_id=child_session.id,
            text=f"[{role}] {text}",
            token_id=token_id,
            request_key=request_key,
        )
        child = AgentTask(
            user_id=user_id,
            workspace_id=workspace_id,
            team_id=team_id,
            parent_id=parent.id,
            role=role,
            title=f"{title[:100]} / {role}",
            input=text,
            status="queued",
            budget={
                "tool_scopes": list(ROLE_SCOPES[role]),
                "max_turns": (budget or {}).get("max_turns", 6),
            },
            session_id=child_session.id,
            run_id=run.id,
        )
        session.add(child)
        await session.flush()  # materialise the UUID before keying the budget row
        await _budget_use(session, child.id)
        children.append(child)
    await session.flush()
    return parent, children


async def get_task(
    session: AsyncSession, *, user_id: str, task_id: str
) -> AgentTask | None:
    return await session.scalar(
        select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == user_id)
    )


async def list_team_tasks(
    session: AsyncSession, *, user_id: str, team_id: str
) -> list[AgentTask]:
    return list(
        await session.scalars(
            select(AgentTask)
            .where(AgentTask.user_id == user_id, AgentTask.team_id == team_id)
            .order_by(AgentTask.created_at, AgentTask.id)
        )
    )


async def append_mail(
    session: AsyncSession,
    *,
    user_id: str,
    team_id: str,
    message_key: str,
    payload: dict,
    citations: list[str] | None = None,
    sender_task_id: str | None = None,
    recipient_task_id: str | None = None,
) -> AgentTeamMessage:
    """Append a mailbox message once; duplicate keys return the stored row."""

    if not message_key or len(message_key) > 128:
        raise MultiAgentConflict("message_key must contain 1-128 characters")
    existing = await session.scalar(
        select(AgentTeamMessage).where(
            AgentTeamMessage.team_id == team_id, AgentTeamMessage.message_key == message_key
        )
    )
    if existing is not None:
        if _digest(existing.payload) != _digest(payload):
            raise MultiAgentConflict("message_key was reused with a different payload")
        return existing
    team_tasks = await list_team_tasks(session, user_id=user_id, team_id=team_id)
    if not team_tasks:
        raise MultiAgentConflict("Team not found")
    message = AgentTeamMessage(
        team_id=team_id,
        task_id=sender_task_id,
        sender_task_id=sender_task_id,
        recipient_task_id=recipient_task_id,
        message_key=message_key,
        payload=payload,
        citations=list(citations or []),
    )
    session.add(message)
    await session.flush()
    return message


async def read_mail(
    session: AsyncSession, *, user_id: str, team_id: str, recipient_task_id: str | None = None
) -> list[AgentTeamMessage]:
    query = select(AgentTeamMessage).where(AgentTeamMessage.team_id == team_id)
    if recipient_task_id:
        query = query.where(
            (AgentTeamMessage.recipient_task_id == recipient_task_id)
            | (AgentTeamMessage.recipient_task_id.is_(None))
        )
    return list(
        await session.scalars(query.order_by(AgentTeamMessage.created_at, AgentTeamMessage.id))
    )


async def _verified_citations(
    session: AsyncSession, *, user_id: str, citations: list[str]
) -> tuple[list[str], list[str]]:
    if not citations:
        return [], []
    found = set(
        await session.scalars(
            select(Evidence.id).where(Evidence.user_id == user_id, Evidence.id.in_(citations))
        )
    )
    return sorted(found), sorted(set(citations) - found)


async def project_result(
    session: AsyncSession, *, user_id: str, task: AgentTask
) -> dict:
    """Bound a child result and drop citations that no longer exist."""

    result = task.result or {}
    text = str(result.get("text", ""))[:MAX_PROJECTION_CHARS]
    raw_citations = [str(value) for value in result.get("citations", []) or []]
    verified, unverified = await _verified_citations(
        session, user_id=user_id, citations=raw_citations
    )
    return {
        "task_id": task.id,
        "role": task.role,
        "status": task.status,
        "text": text,
        "citations": verified,
        "unverified_citations": unverified,
        "truncated": len(str(result.get("text", ""))) > MAX_PROJECTION_CHARS,
    }


async def record_budget(
    session: AsyncSession,
    *,
    task_id: str,
    attempts: int = 0,
    usage: dict[str, int] | None = None,
    estimated_cost_usd: float = 0.0,
) -> AgentTaskBudgetUse:
    """Additive budget accounting; callers never overwrite prior attempts."""

    record = await _budget_use(session, task_id)
    record.attempts += max(0, attempts)
    record.input_tokens += max(0, int((usage or {}).get("input_tokens", 0)))
    record.output_tokens += max(0, int((usage or {}).get("output_tokens", 0)))
    record.estimated_cost_usd = round(record.estimated_cost_usd + max(0.0, estimated_cost_usd), 8)
    await session.flush()
    return record


async def _cancel_run(session: AsyncSession, run_id: str | None, *, reason: str) -> None:
    if not run_id:
        return
    run = await session.get(AgentRun, run_id)
    if run is None or run.status in TERMINAL_RUN_STATES:
        return
    await store._append(session, run, None, "run.cancelled", {"reason": reason})
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status.not_in(TERMINAL_RUN_STATES))
        .values(status="cancelled", error_code=reason, lease_owner=None, lease_until=None)
    )


async def cancel_task_tree(
    session: AsyncSession, *, user_id: str, task_id: str
) -> AgentTask | None:
    root = await get_task(session, user_id=user_id, task_id=task_id)
    if root is None:
        return None
    children = list(
        await session.scalars(
            select(AgentTask).where(
                AgentTask.parent_id == task_id, AgentTask.user_id == user_id
            )
        )
    )
    for child in children:
        await _cancel_run(session, child.run_id, reason="parent_cancelled")
        child.status = "cancelled"
        child.error = "parent_cancelled"
    await _cancel_run(session, root.run_id, reason="cancelled_by_user")
    root.status = "cancelled"
    root.error = "cancelled_by_user"
    root.result = {"reason": "cancelled_by_user", "cancelled_children": len(children)}
    await session.flush()
    await session.refresh(root)
    return root


async def refresh_parent(
    session: AsyncSession, *, user_id: str, parent_id: str
) -> AgentTask | None:
    """Project finished children onto a waiting parent; no deadlock waiting."""

    parent = await get_task(session, user_id=user_id, task_id=parent_id)
    if parent is None or parent.status != "waiting":
        return parent
    children = list(
        await session.scalars(
            select(AgentTask).where(
                AgentTask.parent_id == parent_id, AgentTask.user_id == user_id
            )
        )
    )
    if not children or any(child.status not in TERMINAL_TASK_STATES for child in children):
        return parent
    projections = [await project_result(session, user_id=user_id, task=child) for child in children]
    statuses = {child.status for child in children}
    parent.status = (
        "succeeded" if statuses == {"succeeded"} else
        "cancelled" if "cancelled" in statuses else "failed"
    )
    parent.result = {
        "children": projections,
        "projection_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if parent.status != "succeeded":
        parent.error = "child_task_failed"
    await session.flush()
    return parent
