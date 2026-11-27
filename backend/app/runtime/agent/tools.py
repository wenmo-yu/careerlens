"""Read-only career tools exposed to the agent loop.

Every tool is registered with a JSON schema, a side-effect class and the scope
it needs. Identity always comes from the capability, never from model-supplied
arguments. M3 deliberately ships read-only tools only; write tools require the
M5 approval and sandbox gates.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.retrieval.service import search_evidence
from app.services.profile import read_profile

ToolHandler = Callable[[AsyncSession, str, dict], Awaitable[dict]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict
    side_effect: str
    scope: str
    handler: ToolHandler


class ToolRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def _search_evidence(
    session: AsyncSession, user_id: str, args: dict[str, Any]
) -> dict:
    query = str(args.get("query", "")).strip()
    if not query or len(query) > 2000:
        raise ToolRejected("invalid_args", "query must contain 1-2000 characters")
    limit = int(args.get("limit", 5))
    if not 1 <= limit <= 20:
        raise ToolRejected("invalid_args", "limit must be between 1 and 20")
    items, diagnostics = await search_evidence(
        user_id=user_id, query=query, session=session, limit=limit
    )
    return {
        "items": [
            {
                "evidence_id": item.get("evidence_id"),
                "source_name": item.get("source_name"),
                "source_type": item.get("source_type"),
                "content": item.get("content"),
            }
            for item in items
        ],
        "retrieval": diagnostics,
    }


async def _get_profile(session: AsyncSession, user_id: str, args: dict[str, Any]) -> dict:
    items = await read_profile(session, user_id)
    return {
        "items": [
            {
                "category": item.category,
                "name": item.name,
                "level": item.level,
                "confidence": item.confidence,
                "evidence_ids": item.evidence_ids,
            }
            for item in items
        ]
    }


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            name="search_evidence",
            description="Search the user's career evidence for a claim or requirement.",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            side_effect="read",
            scope="read",
            handler=_search_evidence,
        ),
        ToolSpec(
            name="get_profile",
            description="Read structured profile items with their supporting evidence ids.",
            schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            side_effect="read",
            scope="read",
            handler=_get_profile,
        ),
    )
}


def definitions() -> list[dict]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.schema,
            "side_effect": spec.side_effect,
        }
        for spec in TOOLS.values()
    ]


async def invoke(
    session: AsyncSession, *, user_id: str, name: str, args: dict[str, Any], run_id: str
) -> dict:
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolRejected("unknown_tool", f"Tool is not registered: {name}")
    if spec.side_effect != "read":
        raise ToolRejected("approval_required", "Only read-only tools are enabled in M3")
    # Model-supplied identity is never authoritative; reject it loudly so the
    # failure is visible in tests instead of silently ignored.
    for forbidden in ("user_id", "workspace_id", "session_id"):
        if forbidden in args:
            raise ToolRejected("identity_in_args", f"{forbidden} must not be supplied by the model")
    try:
        result = await spec.handler(session, user_id, args)
    except ToolRejected:
        raise
    except (TypeError, ValueError) as exc:
        raise ToolRejected("invalid_args", str(exc)) from exc
    session.add(
        AuditEvent(
            user_id=user_id,
            action=f"agent.tool.{name}",
            resource_type="agent_run",
            resource_id=run_id,
            details={"side_effect": spec.side_effect},
        )
    )
    await session.flush()
    return result
