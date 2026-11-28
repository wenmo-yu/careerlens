"""Workspace-scoped file broker for the agent plane.

The broker is deliberately narrow: files must live under an explicitly
configured workspace root, use relative POSIX-style paths, avoid symlinks and
junctions, stay inside a small extension/size budget, and never expose ADS or
UNC paths. Write calls are approved and recorded in the durable tool ledger,
so a replay cannot repeat the side effect.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent import AgentToolLedger


@dataclass
class BrokerRejected(Exception):
    code: str
    message: str
    persist: bool = False

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class _Policy:
    root: Path
    extensions: frozenset[str]
    max_bytes: int


def _policy() -> _Policy:
    settings = get_settings()
    raw_root = str(getattr(settings, "agent_workspace_root", "") or "").strip()
    if not raw_root:
        raise BrokerRejected("workspace_not_configured", "No agent workspace root is configured")
    root = Path(raw_root).expanduser().resolve(strict=False)
    if not root.is_dir():
        raise BrokerRejected("workspace_not_configured", "Agent workspace root is not a directory")
    extensions = frozenset(
        item.strip().lower()
        for item in str(getattr(settings, "agent_file_allow_extensions", "")).split(",")
        if item.strip()
    )
    return _Policy(root=root, extensions=extensions, max_bytes=int(settings.agent_file_max_bytes))


def _resolve(policy: _Policy, relative: str, *, writing: bool) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise BrokerRejected("invalid_args", "path must be a non-empty relative path")
    value = relative.strip()
    if "\x00" in value or ":" in value or "\\" in value or value.startswith("//"):
        raise BrokerRejected("path_denied", "absolute, UNC, ADS or Windows-style paths are denied")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise BrokerRejected("path_denied", "path must be a clean relative POSIX path")
    suffix = Path(parts[-1]).suffix.lower()
    if policy.extensions and suffix not in policy.extensions:
        raise BrokerRejected("extension_denied", f"extension {suffix or '<none>'} is not allowed")

    raw = policy.root.joinpath(*parts)
    for parent in (raw, *raw.parents):
        if parent == policy.root:
            break
        if parent.is_symlink():
            raise BrokerRejected("path_denied", "symlinked paths are denied")
    candidate = raw.resolve(strict=False)
    if not candidate.is_relative_to(policy.root):
        raise BrokerRejected("path_denied", "path escapes the workspace root")
    if candidate.exists() and not candidate.is_file():
        raise BrokerRejected("path_denied", "path is not a regular file")
    if writing and raw.is_symlink():
        raise BrokerRejected("path_denied", "writing through a symlink is denied")
    return candidate


async def _prior_ledger(
    session: AsyncSession, *, run_id: str, invocation_id: str | None, digest: str
) -> AgentToolLedger | None:
    if not invocation_id:
        return None
    prior = await session.scalar(
        select(AgentToolLedger).where(
            AgentToolLedger.run_id == run_id,
            AgentToolLedger.invocation_id == invocation_id,
        )
    )
    if prior is not None and (
        prior.args_digest != digest or prior.tool != "write_workspace_file"
    ):
        raise BrokerRejected(
            "tool_ledger_conflict", "invocation was already recorded by another tool or digest"
        )
    if prior is not None and prior.status == "succeeded":
        return prior
    if prior is not None:
        raise BrokerRejected(
            "tool_ledger_incomplete", f"invocation is already {prior.status}"
        )
    return None


async def read_file(
    session: AsyncSession, user_id: str, args: dict[str, Any], context: Any
) -> dict:
    del session, user_id, context
    policy = _policy()
    path = _resolve(policy, str(args.get("path", "")), writing=False)
    if not path.exists():
        raise BrokerRejected("file_not_found", "file does not exist")
    data = path.read_bytes()
    if len(data) > policy.max_bytes:
        raise BrokerRejected("file_too_large", "file exceeds the workspace budget")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BrokerRejected("invalid_encoding", "file is not valid UTF-8") from exc
    max_chars = max(1, policy.max_bytes)
    if len(text) > max_chars:
        raise BrokerRejected("file_too_large", "file exceeds the workspace budget")
    return {"path": str(args["path"]).strip(), "content": text, "bytes": len(data)}


async def write_file(
    session: AsyncSession, user_id: str, args: dict[str, Any], context: Any
) -> dict:
    policy = _policy()
    path = _resolve(policy, str(args.get("path", "")), writing=True)
    content = str(args.get("content", ""))
    data = content.encode("utf-8")
    if not data or len(data) > policy.max_bytes:
        raise BrokerRejected("file_too_large", "content must fit the workspace byte budget")

    prior = await _prior_ledger(
        session,
        run_id=context.run_id,
        invocation_id=context.invocation_id,
        digest=context.args_digest,
    )
    if prior is not None:
        return dict(prior.result or {})

    ledger = AgentToolLedger(
        user_id=user_id,
        session_id=context.session_id or None,
        run_id=context.run_id,
        invocation_id=context.invocation_id or "",
        tool="write_workspace_file",
        args_digest=context.args_digest,
        approval_id=context.approval_id,
        status="pending",
    )
    session.add(ledger)
    await session.flush()
    try:
        overwritten = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        for parent in (path.parent, *path.parent.parents):
            if parent == policy.root:
                break
            if parent.is_symlink():
                raise BrokerRejected("path_denied", "symlinked parent is denied")
        descriptor, temp_name = tempfile.mkstemp(prefix=".agent-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        result = {"path": str(args["path"]).strip(), "bytes": len(data), "overwritten": overwritten}
        ledger.status = "succeeded"
        ledger.result = result
        await session.flush()
        return result
    except BrokerRejected:
        ledger.status = "failed"
        ledger.error = "path_denied"
        await session.flush()
        raise
    except Exception as exc:
        ledger.status = "failed"
        ledger.error = f"{type(exc).__name__}: {exc}"[:500]
        await session.flush()
        raise BrokerRejected(
            "tool_write_failed", "workspace file write failed", persist=True
        ) from exc
