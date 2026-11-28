"""Career tools exposed to the agent loop.

Every tool is registered with a JSON schema, a side-effect class and the scope
it needs. Identity always comes from the capability, never from model-supplied
arguments. Read tools keep their original behaviour; write tools require a
matching, approved ledger entry and are deduplicated by invocation id.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentApproval, AgentArtifact, AgentToolLedger
from app.models.audit import AuditEvent
from app.models.evidence import Evidence
from app.retrieval.service import search_evidence
from app.runtime.agent import file_broker
from app.services.profile import read_profile

MAX_NOTE_TITLE = 200
MAX_NOTE_CONTENT = 20_000
MAX_EVIDENCE_IDS = 50


@dataclass(frozen=True)
class ToolContext:
    """Trusted execution context; the model never controls these fields."""

    run_id: str
    session_id: str = ""
    invocation_id: str | None = None
    approval_id: str | None = None
    approved: bool = False
    args_digest: str = ""


ToolHandler = Callable[[AsyncSession, str, dict, ToolContext], Awaitable[dict]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict
    side_effect: str
    scope: str
    handler: ToolHandler


class ToolRejected(Exception):
    def __init__(self, code: str, message: str, *, persist: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        # True when a durable failure record was written and must survive the
        # gateway's error path (which otherwise rolls the transaction back).
        self.persist = persist


def digest_args(args: dict) -> str:
    """Canonical digest shared by the CLI and the gateway."""

    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _search_evidence(
    session: AsyncSession, user_id: str, args: dict[str, Any], _context: ToolContext
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


async def _get_profile(
    session: AsyncSession, user_id: str, args: dict[str, Any], _context: ToolContext
) -> dict:
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


async def _save_career_note(
    session: AsyncSession, user_id: str, args: dict[str, Any], context: ToolContext
) -> dict:
    """Write one note and its ledger entry in a single transaction.

    The ledger is the idempotency authority: the same invocation with the same
    digest returns the stored result without creating a second artifact.
    """

    title = str(args.get("title", "")).strip()
    content = str(args.get("content", ""))
    raw_evidence = args.get("evidence_ids", []) or []
    if not title or len(title) > MAX_NOTE_TITLE:
        raise ToolRejected("invalid_args", f"title must contain 1-{MAX_NOTE_TITLE} characters")
    if not content or len(content) > MAX_NOTE_CONTENT:
        raise ToolRejected(
            "invalid_args", f"content must contain 1-{MAX_NOTE_CONTENT} characters"
        )
    if not isinstance(raw_evidence, list) or len(raw_evidence) > MAX_EVIDENCE_IDS:
        raise ToolRejected(
            "invalid_args", f"evidence_ids must be a list of at most {MAX_EVIDENCE_IDS} ids"
        )
    if any(not isinstance(item, str) or not item for item in raw_evidence):
        raise ToolRejected("invalid_args", "evidence_ids must contain non-empty strings")
    evidence_ids = list(dict.fromkeys(raw_evidence))
    if evidence_ids:
        visible = set(
            await session.scalars(
                select(Evidence.id).where(
                    Evidence.user_id == user_id, Evidence.id.in_(evidence_ids)
                )
            )
        )
        missing = [item for item in evidence_ids if item not in visible]
        if missing:
            raise ToolRejected(
                "invalid_args", "evidence_ids must reference the current user's evidence"
            )

    existing = await session.scalar(
        select(AgentToolLedger).where(
            AgentToolLedger.run_id == context.run_id,
            AgentToolLedger.invocation_id == context.invocation_id,
        )
    )
    if existing is not None:
        if existing.args_digest != context.args_digest:
            raise ToolRejected(
                "tool_ledger_conflict", "invocation was already recorded with a different digest"
            )
        if existing.status != "succeeded":
            raise ToolRejected(
                "tool_ledger_incomplete",
                f"invocation is already {existing.status}; refusing to report a result",
            )
        return dict(existing.result or {})

    ledger = AgentToolLedger(
        user_id=user_id,
        session_id=context.session_id or None,
        run_id=context.run_id,
        invocation_id=context.invocation_id or "",
        tool="save_career_note",
        args_digest=context.args_digest,
        approval_id=context.approval_id,
        status="pending",
    )
    session.add(ledger)
    await session.flush()
    try:
        artifact = AgentArtifact(
            user_id=user_id,
            session_id=context.session_id or None,
            run_id=context.run_id,
            kind="career_note",
            title=title,
            content=content,
            citations=[{"evidence_id": item} for item in evidence_ids],
        )
        session.add(artifact)
        await session.flush()
        result = {
            "artifact_id": artifact.id,
            "title": title,
            "evidence_count": len(evidence_ids),
        }
        ledger.status = "succeeded"
        ledger.result = result
        ledger.error = None
        await session.flush()
        return result
    except Exception as exc:  # a failed write is never reported as a success
        ledger.status = "failed"
        ledger.error = f"{type(exc).__name__}: {exc}"[:500]
        await session.flush()
        raise ToolRejected("tool_write_failed", "artifact write failed", persist=True) from exc


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
        ToolSpec(
            name="save_career_note",
            description="Save a career note with optional references to the user's evidence.",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": MAX_NOTE_TITLE},
                    "content": {"type": "string", "minLength": 1, "maxLength": MAX_NOTE_CONTENT},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "maxItems": MAX_EVIDENCE_IDS,
                    },
                },
                "required": ["title", "content"],
                "additionalProperties": False,
            },
            side_effect="write",
            scope="agent.artifact.write",
            handler=_save_career_note,
        ),
        ToolSpec(
            name="read_workspace_file",
            description="Read a small UTF-8 file from the configured agent workspace.",
            schema={
                "type": "object",
                "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 500}},
                "required": ["path"],
                "additionalProperties": False,
            },
            side_effect="read",
            scope="workspace.read",
            handler=file_broker.read_file,
        ),
        ToolSpec(
            name="write_workspace_file",
            description="Write a small UTF-8 file inside the configured agent workspace.",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 500},
                    "content": {"type": "string", "minLength": 1, "maxLength": 1_048_576},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            side_effect="write",
            scope="workspace.write",
            handler=file_broker.write_file,
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


def read_tools() -> list[str]:
    return sorted(name for name, spec in TOOLS.items() if spec.side_effect == "read")


def write_tools() -> list[str]:
    return sorted(name for name, spec in TOOLS.items() if spec.side_effect == "write")


async def invoke(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    args: dict[str, Any],
    run_id: str,
    session_id: str = "",
    invocation_id: str | None = None,
    approval_id: str | None = None,
    approved: bool = False,
    args_digest: str | None = None,
) -> dict:
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolRejected("unknown_tool", f"Tool is not registered: {name}")
    # Model-supplied identity is never authoritative; reject it loudly so the
    # failure is visible in tests instead of silently ignored.
    for forbidden in ("user_id", "workspace_id", "session_id"):
        if forbidden in args:
            raise ToolRejected("identity_in_args", f"{forbidden} must not be supplied by the model")

    digest = args_digest or digest_args(args)
    context = ToolContext(
        run_id=run_id,
        session_id=session_id,
        invocation_id=invocation_id,
        approval_id=approval_id,
        approved=approved,
        args_digest=digest,
    )
    if spec.side_effect == "write":
        prior = await session.scalar(
            select(AgentToolLedger).where(
                AgentToolLedger.run_id == run_id,
                AgentToolLedger.invocation_id == (invocation_id or ""),
            )
        )
        if prior is not None and (
            prior.args_digest != digest or prior.tool != name
        ):
            raise ToolRejected(
                "tool_ledger_conflict", "invocation was already recorded by another tool or digest"
            )
        if not invocation_id or not approval_id or not approved:
            raise ToolRejected("approval_required", "Write tools require an approved invocation")
        approval = await session.scalar(
            select(AgentApproval).where(
                AgentApproval.id == approval_id,
                AgentApproval.run_id == run_id,
                AgentApproval.user_id == user_id,
                AgentApproval.invocation_id == invocation_id,
                AgentApproval.args_digest == digest,
                AgentApproval.status == "approved",
            )
        )
        if approval is None:
            raise ToolRejected(
                "approval_mismatch", "Approval does not match this write invocation"
            )
    elif spec.side_effect != "read":
        raise ToolRejected("approval_required", f"Unsupported side effect: {spec.side_effect}")

    try:
        result = await spec.handler(session, user_id, args, context)
    except ToolRejected:
        raise
    except file_broker.BrokerRejected as exc:
        raise ToolRejected(exc.code, exc.message, persist=exc.persist) from exc
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
