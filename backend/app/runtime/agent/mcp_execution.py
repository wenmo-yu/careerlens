"""Controlled MCP tool execution adapter (M8).

Every tool call whose name carries a connector namespace must pass the
connector admission gate before any execution is attempted. There is no real
MCP client here: with no sandbox and no reviewed executor, an admitted tool
returns a structured ``execution_unavailable`` result instead of silently
running or being mistaken for a built-in tool.

This is deliberately conservative: default deny, identity from the trusted
capability context, and no third-party code or network access.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_connector import AgentMcpConnector
from app.runtime.agent import mcp_connectors as admission


@dataclass(frozen=True)
class McpDecision:
    handled: bool
    ok: bool
    code: str
    message: str


def is_mcp_tool(name: str) -> bool:
    """A namespaced tool name looks like '<namespace>.<tool>'."""

    return isinstance(name, str) and "." in name and admission.NAMESPACE_RE.match(
        name.split(".", 1)[0]
    ) is not None


async def execute(
    session: AsyncSession,
    *,
    user_id: str,
    qualified_name: str,
    config_digest_supplied: str | None = None,
    # Caller scopes come from the trusted invocation context, never the model.
    caller_scopes: tuple[str, ...] | set[str] = ("read",),
) -> McpDecision:
    """Admit a namespaced MCP tool; never execute code or open a connection."""

    namespace = qualified_name.split(".", 1)[0]
    record = await session.scalar(
        select(AgentMcpConnector).where(
            AgentMcpConnector.user_id == user_id,
            AgentMcpConnector.namespace == namespace,
        )
    )
    if record is None:
        return McpDecision(True, False, "connector_not_found", "No such connector")
    allowed, reason = admission.admit(
        record,
        qualified_name=qualified_name,
        caller_scopes=caller_scopes,
        config_digest_supplied=config_digest_supplied,
    )
    if not allowed:
        return McpDecision(True, False, reason, "MCP tool was not admitted")
    # Admitted, but no reviewed executor/OS sandbox is available: fail closed
    # with an explicit, structured result rather than pretending success.
    return McpDecision(
        True,
        False,
        "execution_unavailable",
        "MCP execution requires an OS sandbox and a reviewed executor (not available)",
    )
