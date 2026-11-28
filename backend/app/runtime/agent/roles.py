"""Durable long-lived roles with versioned config and a narrowed tool set (M8).

A role is a persistence boundary, not a new identity. It binds one long-lived
agent session, records an immutable config version per run, and may only offer
tools that exist in the global registry. Write tools keep the normal approval
and ledger gates; a role never bypasses them and never sends on behalf of
another user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import AgentRole
from app.runtime.agent import store
from app.runtime.agent import tools as tool_registry

ROLE_TEMPLATES: dict[str, dict] = {
    "evidence_researcher": {
        "prompt": "你是证据研究员。只依据用户可访问的证据回答问题，每条结论给出 evidence_id。",
        "tool_allowlist": ["search_evidence", "get_profile"],
    },
    "job_analyst": {
        "prompt": "你是岗位分析员。阅读 JD 与画像，区分必需/加分要求，指出缺口与不确定性。",
        "tool_allowlist": ["search_evidence", "get_profile"],
    },
    "learning_planner": {
        "prompt": "你是学习规划员。依据证据与缺口制定可执行的学习阶段，不编造经历。",
        "tool_allowlist": ["search_evidence", "get_profile"],
    },
    "evidence_reviewer": {
        "prompt": "你是证据审查员。核对结论与证据的一致性，指出无支持或被删除的引用。",
        "tool_allowlist": ["search_evidence", "get_profile"],
    },
    "career_coach": {
        "prompt": "你是职业教练。综合已核验事实给出建议，明确区分事实、自陈与推断。",
        "tool_allowlist": ["search_evidence", "get_profile"],
    },
}

MAX_PROMPT = 20_000
MAX_BUDGET_TURNS = 24
MAX_NAME = 120


class RoleConflict(ValueError):
    """Role input or state contradicts durable facts."""


def _clean_allowlist(raw: list[str]) -> list[str]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RoleConflict("tool_allowlist must be a list")
    cleaned = list(dict.fromkeys(str(item) for item in raw if item))
    unknown = [name for name in cleaned if name not in tool_registry.TOOLS]
    if unknown:
        raise RoleConflict(f"unknown_tool: {', '.join(unknown)}")
    return cleaned


async def create_role(
    session: AsyncSession,
    *,
    user_id: str,
    workspace_id: str,
    name: str,
    template: str,
    prompt: str | None,
    tool_allowlist: list[str] | None,
    model_policy: dict | None = None,
    budget: dict | None = None,
    output_schema: dict | None = None,
    actor_token_id: str | None,
) -> AgentRole:
    clean_name = str(name).strip()
    if not clean_name or len(clean_name) > MAX_NAME:
        raise RoleConflict(f"name must contain 1-{MAX_NAME} characters")
    if template not in ROLE_TEMPLATES:
        raise RoleConflict("invalid_config: unsupported role template")
    base = ROLE_TEMPLATES[template]
    role_prompt = str(prompt or base["prompt"]).strip()
    if not role_prompt or len(role_prompt) > MAX_PROMPT:
        raise RoleConflict(f"prompt must contain 1-{MAX_PROMPT} characters")
    allowlist = _clean_allowlist(
        tool_allowlist if tool_allowlist is not None else base["tool_allowlist"]
    )
    clean_budget = dict(budget or {})
    max_turns = int(clean_budget.get("max_turns", 6))
    if not 1 <= max_turns <= MAX_BUDGET_TURNS:
        raise RoleConflict(f"budget.max_turns must be between 1 and {MAX_BUDGET_TURNS}")
    clean_budget["max_turns"] = max_turns

    existing = await session.scalar(
        select(AgentRole).where(AgentRole.user_id == user_id, AgentRole.name == clean_name)
    )
    if existing is not None:
        raise RoleConflict("role_name_conflict")

    persistent = await store.create_session(
        session, user_id=user_id, title=f"角色：{clean_name[:60]}", workspace_id=workspace_id
    )
    record = AgentRole(
        user_id=user_id,
        workspace_id=workspace_id,
        name=clean_name,
        template=template,
        version=1,
        prompt=role_prompt,
        tool_allowlist=allowlist,
        model_policy=dict(model_policy or {}),
        budget=clean_budget,
        output_schema=dict(output_schema or {}),
        state="active",
        session_id=persistent.id,
        actor_token_id=actor_token_id,
    )
    session.add(record)
    await session.flush()
    return record


async def list_roles(session: AsyncSession, *, user_id: str) -> list[AgentRole]:
    return list(
        await session.scalars(
            select(AgentRole)
            .where(AgentRole.user_id == user_id)
            .order_by(AgentRole.name, AgentRole.id)
        )
    )


async def get_role(
    session: AsyncSession, *, user_id: str, role_id: str
) -> AgentRole | None:
    return await session.scalar(
        select(AgentRole).where(AgentRole.id == role_id, AgentRole.user_id == user_id)
    )


async def update_role(
    session: AsyncSession,
    *,
    user_id: str,
    role_id: str,
    prompt: str | None = None,
    tool_allowlist: list[str] | None = None,
    model_policy: dict | None = None,
    budget: dict | None = None,
    output_schema: dict | None = None,
) -> AgentRole | None:
    record = await get_role(session, user_id=user_id, role_id=role_id)
    if record is None:
        return None
    if prompt is not None:
        clean = str(prompt).strip()
        if not clean or len(clean) > MAX_PROMPT:
            raise RoleConflict(f"prompt must contain 1-{MAX_PROMPT} characters")
        record.prompt = clean
    if tool_allowlist is not None:
        record.tool_allowlist = _clean_allowlist(tool_allowlist)
    if model_policy is not None:
        if not isinstance(model_policy, dict):
            raise RoleConflict("model_policy must be an object")
        record.model_policy = dict(model_policy)
    if budget is not None:
        if not isinstance(budget, dict):
            raise RoleConflict("budget must be an object")
        max_turns = int(budget.get("max_turns", record.budget.get("max_turns", 6)))
        if not 1 <= max_turns <= MAX_BUDGET_TURNS:
            raise RoleConflict(f"budget.max_turns must be between 1 and {MAX_BUDGET_TURNS}")
        clean_budget = dict(budget)
        clean_budget["max_turns"] = max_turns
        record.budget = clean_budget
    if output_schema is not None:
        if not isinstance(output_schema, dict):
            raise RoleConflict("output_schema must be an object")
        record.output_schema = dict(output_schema)
    record.version += 1
    await session.flush()
    await session.refresh(record)
    return record


async def set_state(
    session: AsyncSession, *, user_id: str, role_id: str, state: str
) -> AgentRole | None:
    if state not in ("active", "paused", "archived"):
        raise RoleConflict("state must be active, paused or archived")
    record = await get_role(session, user_id=user_id, role_id=role_id)
    if record is None:
        return None
    record.state = state
    await session.flush()
    await session.refresh(record)
    return record


def role_snapshot(record: AgentRole) -> dict:
    """The frozen config a run records; the gateway enforces the allowlist."""

    return {
        "role_id": record.id,
        "role_version": record.version,
        "template": record.template,
        "tool_allowlist": list(record.tool_allowlist),
        "model_policy": dict(record.model_policy),
        "budget": dict(record.budget),
        "output_schema": dict(record.output_schema),
    }


async def trigger(
    session: AsyncSession,
    *,
    user_id: str,
    role_id: str,
    text: str,
    request_key: str,
    actor_token_id: str | None,
) -> tuple[AgentRole, object, bool]:
    """Submit one ordinary turn into the role's persistent session.

    The role itself performs no external action; it only narrows the tools that
    the ordinary agent run may offer. A revoked actor token pauses the role so
    it cannot keep being triggered without consent.
    """

    record = await get_role(session, user_id=user_id, role_id=role_id)
    if record is None:
        raise RoleConflict("role_not_found")
    if record.state != "active":
        raise RoleConflict("role_inactive")
    turn = str(text).strip()
    if not turn or len(turn) > MAX_PROMPT:
        raise RoleConflict("invalid_config: text must contain 1-20000 characters")
    if record.session_id is None:
        raise RoleConflict("role_inactive: role has no persistent session")
    run, created = await store.submit_turn(
        session,
        user_id=user_id,
        session_id=record.session_id,
        text=turn,
        token_id=actor_token_id or record.actor_token_id,
        request_key=request_key,
    )
    if created:
        payload = dict(run.payload or {})
        payload["role"] = role_snapshot(record)
        run.payload = payload
        await session.flush()
    return record, run, created
