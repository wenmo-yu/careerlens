"""Daemon control contract (v1).

The published contract lives in `contracts/daemon-control-v1.json`. A frozen
built-in copy is kept here because a packaged daemon has no repository checkout
next to it: the file is read when available, otherwise the built-in copy is
used. `tests/test_daemon_contract.py` asserts the two stay identical.

Keep this module free of Windows-only imports so it can be imported and tested
on every platform.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROTOCOL = 1
SUPPORTED_PROTOCOLS = (1,)
CONTRACT_FILE = "daemon-control-v1.json"

BUILTIN_COMMANDS: dict[str, tuple[str, ...]] = {
    "hello": ("protocol", "client"),
    "ping": (),
    "status": (),
    "restart": ("role",),
    "stop": (),
}
BUILTIN_ERROR_CODES = frozenset(
    {
        "unknown_command",
        "invalid_params",
        "unknown_role",
        "protocol_mismatch",
        "not_ready",
        "internal_error",
        "frame_too_large",
    }
)
BUILTIN_ROLES = ("api", "worker")

DEFAULT_PIPE_NAME = r"\\.\pipe\careerlens-daemon"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    required_params: tuple[str, ...]


@dataclass(frozen=True)
class Contract:
    protocol: int
    commands: dict[str, CommandSpec]
    error_codes: frozenset[str]
    restart_roles: tuple[str, ...]
    source: str

    def command(self, name: str) -> CommandSpec | None:
        return self.commands.get(name)


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get("CAREERLENS_DAEMON_CONTRACT")
    if override:
        paths.append(Path(override))
    # backend/app/runtime/daemon/contract.py -> <repo>/contracts/daemon-control-v1.json
    paths.append(Path(__file__).resolve().parents[4] / "contracts" / CONTRACT_FILE)
    return paths


def builtin_contract() -> Contract:
    return Contract(
        protocol=PROTOCOL,
        commands={name: CommandSpec(name, required) for name, required in BUILTIN_COMMANDS.items()},
        error_codes=BUILTIN_ERROR_CODES,
        restart_roles=BUILTIN_ROLES,
        source="builtin",
    )


def _parse(payload: dict, source: str) -> Contract:
    version = payload.get("version")
    if version != PROTOCOL:
        raise ValueError(f"daemon contract version {version!r} is not supported")
    commands = {
        entry["name"]: CommandSpec(entry["name"], tuple(entry.get("params_required", ())))
        for entry in payload["commands"]
    }
    error_codes = frozenset(entry["code"] for entry in payload["error_codes"])
    roles: tuple[str, ...] = BUILTIN_ROLES
    for entry in payload["commands"]:
        allowed = entry.get("allowed_roles")
        if allowed:
            roles = tuple(allowed)
    return Contract(
        protocol=version,
        commands=commands,
        error_codes=error_codes,
        restart_roles=roles,
        source=source,
    )


def load_contract() -> Contract:
    """Read the published contract, falling back to the built-in copy."""
    for path in _candidate_paths():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return _parse(payload, str(path))
    return builtin_contract()
