"""MCP connector admission policy (M8). Default deny, no execution (M8 policy).

This module never connects to an MCP server. It records a reviewed connector
configuration and answers one question deterministically: given a trusted
caller scope, is a fully-qualified tool name admitted? Everything else —
network, process isolation, third-party code — is out of scope and requires an
OS sandbox that is not yet verified.
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_connector import AgentMcpConnector

NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
VALID_SCOPES = ("read", "write", "manage")
MAX_TOOLS = 50


class ConnectorConflict(ValueError):
    """Connector input or state contradicts the admission policy."""


def config_digest(*, namespace: str, allowed_tools: list[str], required_scope: str) -> str:
    """Fingerprint the exact reviewed configuration."""

    canonical = json.dumps(
        {
            "namespace": namespace,
            "allowed_tools": sorted(allowed_tools),
            "required_scope": required_scope,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validate(namespace: str, allowed_tools: list[str], required_scope: str) -> list[str]:
    if not NAMESPACE_RE.match(namespace):
        raise ConnectorConflict("invalid_config: bad namespace")
    if not isinstance(allowed_tools, list) or not 1 <= len(allowed_tools) <= MAX_TOOLS:
        raise ConnectorConflict(f"allowed_tools must contain 1-{MAX_TOOLS} tools")
    clean = list(dict.fromkeys(str(name) for name in allowed_tools))
    if any(not TOOL_RE.match(name) for name in clean):
        raise ConnectorConflict("invalid_config: bad tool name")
    if required_scope not in VALID_SCOPES:
        raise ConnectorConflict("invalid_config: bad required_scope")
    return clean


async def register(
    session: AsyncSession,
    *,
    user_id: str,
    workspace_id: str,
    namespace: str,
    allowed_tools: list[str],
    required_scope: str = "read",
) -> AgentMcpConnector:
    clean_tools = _validate(namespace, allowed_tools, required_scope)
    existing = await session.scalar(
        select(AgentMcpConnector).where(
            AgentMcpConnector.user_id == user_id,
            AgentMcpConnector.namespace == namespace,
        )
    )
    if existing is not None:
        raise ConnectorConflict("connector already registered for this namespace")
    record = AgentMcpConnector(
        user_id=user_id,
        workspace_id=workspace_id,
        namespace=namespace,
        allowed_tools=clean_tools,
        required_scope=required_scope,
        config_digest=config_digest(
            namespace=namespace,
            allowed_tools=clean_tools,
            required_scope=required_scope,
        ),
        # Registered is NOT enabled: enabling is a separate explicit action.
        state="registered",
    )
    session.add(record)
    await session.flush()
    return record


async def list_connectors(
    session: AsyncSession, *, user_id: str
) -> list[AgentMcpConnector]:
    return list(
        await session.scalars(
            select(AgentMcpConnector)
            .where(AgentMcpConnector.user_id == user_id)
            .order_by(AgentMcpConnector.namespace)
        )
    )


async def get_connector(
    session: AsyncSession, *, user_id: str, connector_id: str
) -> AgentMcpConnector | None:
    return await session.scalar(
        select(AgentMcpConnector).where(
            AgentMcpConnector.id == connector_id,
            AgentMcpConnector.user_id == user_id,
        )
    )


async def set_state(
    session: AsyncSession, *, user_id: str, connector_id: str, state: str
) -> AgentMcpConnector | None:
    if state not in ("enabled", "disabled", "registered"):
        raise ConnectorConflict("state must be registered, enabled or disabled")
    record = await get_connector(session, user_id=user_id, connector_id=connector_id)
    if record is None:
        return None
    if record.revoked and state == "enabled":
        raise ConnectorConflict("connector_revoked")
    record.state = state
    await session.flush()
    await session.refresh(record)
    return record


async def revoke(
    session: AsyncSession, *, user_id: str, connector_id: str
) -> AgentMcpConnector | None:
    record = await get_connector(session, user_id=user_id, connector_id=connector_id)
    if record is None:
        return None
    record.revoked = True
    record.state = "disabled"
    await session.flush()
    await session.refresh(record)
    return record


def admit(
    record: AgentMcpConnector,
    *,
    qualified_name: str,
    caller_scopes: set[str] | tuple[str, ...],
    config_digest_supplied: str | None = None,
) -> tuple[bool, str]:
    """Deterministic default-deny admission. No I/O, no side effects."""

    if record.state != "enabled" or record.revoked:
        return False, "connector_disabled"
    if config_digest_supplied is not None and config_digest_supplied != record.config_digest:
        return False, "config_digest_mismatch"
    prefix = f"{record.namespace}."
    if not qualified_name.startswith(prefix):
        return False, "namespace_mismatch"
    short_name = qualified_name[len(prefix) :]
    if short_name not in record.allowed_tools:
        return False, "tool_not_allowed"
    scopes = set(caller_scopes)
    if "manage" not in scopes and record.required_scope not in scopes:
        return False, "scope_insufficient"
    return True, "admitted"
