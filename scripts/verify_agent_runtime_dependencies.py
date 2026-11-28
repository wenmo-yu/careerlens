#!/usr/bin/env python3
"""T27 gate: verify the public repo did not acquire a forbidden Agent SDK.

CareerLens uses a self-developed Agent Core. This check is intentionally
mechanical so it can run in CI: dependency manifests must not contain Pi
packages or OpenAI Agents SDK packages, and no vendored copy may be added.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_DEPENDENCY = re.compile(
    r"(?i)(?:^|[\s\"'/@-])(?:"
    r"@mariozechner/pi-ai|pi-ai|pi-sdk|@openai/agents|openai-agents|openai_agents|"
    r"agents-core|agents_core|@pi-agent|pi-agent-core"
    r")(?:$|[\s\"'/@-])"
)
FORBIDDEN_DIRS = {
    "pi-ai",
    "pi-agent-core",
    "openai-agents",
    "agents-core",
    "vendor/pi",
}
DEPENDENCY_FILES = (
    "frontend/package.json",
    "frontend/pnpm-lock.yaml",
    "backend/pyproject.toml",
    "agent-runtime/package.json",
    "desktop/package.json",
    "package.json",
    "pnpm-lock.yaml",
)
CONTRACTS = (
    "contracts/agent-runtime-v1.json",
    "contracts/daemon-control-v1.json",
    "contracts/runtime-jsonl-v1.methods.json",
)
ADRS = (
    "docs/adr/0001-v4-process-topology-and-ownership.md",
    "docs/adr/0004-m0-scripted-runner-prototype.md",
    "docs/adr/0010-m3-agent-runtime-contract.md",
)


def main() -> int:
    failures: list[str] = []
    checked: list[str] = []

    for relative in DEPENDENCY_FILES:
        path = ROOT / relative
        if not path.exists():
            continue
        checked.append(relative)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN_DEPENDENCY.search(line):
                failures.append(f"{relative}:{number}: forbidden Agent SDK dependency")

    for relative in FORBIDDEN_DIRS:
        if (ROOT / relative).exists():
            failures.append(f"{relative}: forbidden vendored directory")

    for relative in CONTRACTS:
        path = ROOT / relative
        if not path.exists():
            failures.append(f"{relative}: contract is missing")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{relative}: invalid JSON ({exc.msg})")

    for relative in ADRS:
        if not (ROOT / relative).exists():
            failures.append(f"{relative}: ADR is missing")

    if not any((ROOT / "agent-runtime/src/engine").glob("*.ts")):
        failures.append("agent-runtime/src/engine: self-developed engine source is missing")

    print(f"[T27] checked dependency files: {', '.join(checked) or 'none'}")
    if failures:
        for failure in failures:
            print(f"[T27] FAIL {failure}")
        return 1
    print("[T27] PASS no Pi/OpenAI Agents SDK dependency or vendored copy found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
