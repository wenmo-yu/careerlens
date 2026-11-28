"""One-time grant so the agent runtime can start inside the AppContainer.

The container can read ``%SystemRoot%`` by default but not the Python install or
this repository. Granting read/execute has to happen once per install, because
doing it per run would rewrite thousands of ACLs every time.

Usage::

    python tools/sandbox_bootstrap.py --confirm
    python tools/sandbox_bootstrap.py --confirm --verify-only
    python tools/sandbox_bootstrap.py --revoke --confirm

What it grants: read/execute on the interpreter prefix, the active virtualenv
root and ``backend/``. It never grants the parent chain (``icacls`` propagation on
``D:\\work`` or the user profile can take minutes and would expose far more than
needed); if traversal turns out to be blocked, ``--verify`` fails loudly instead
of silently producing a half-working sandbox.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.runtime import sandbox  # noqa: E402

PROBE = (
    "import json,sys;"
    "import httpx, fastapi;"
    "print(json.dumps({'python': sys.version_info[:2], 'httpx': httpx.__version__}))"
)


def runtime_roots() -> list[Path]:
    roots = {Path(sys.base_prefix).resolve(), Path(sys.executable).resolve().parents[1].resolve()}
    return [root for root in roots if root.exists()] + [BACKEND]


def grant_runtime(sid: str) -> list[Path]:
    granted: list[Path] = []
    for root in runtime_roots():
        if not sandbox.has_grant(root, sid):
            sandbox.grant(root, sid, permissions="(OI)(CI)(RX)")
            granted.append(root)
    return granted


def verify() -> dict:

    workspace = BACKEND / ".sandbox-verify"
    workspace.mkdir(exist_ok=True)
    sid = sandbox.ensure_profile()
    sandbox.grant(workspace, sid, permissions="(OI)(CI)(M)")
    try:
        result = sandbox.run(
            [sys.executable, "-c", PROBE],
            cwd=workspace,
            env={"PYTHONPATH": str(BACKEND)},
            timeout=120,
        )
        return {
            "ok": result.ok,
            "exit_code": result.exit_code,
            "stdout": result.stdout.strip()[:500],
            "stderr": result.stderr.strip()[-800:],
        }
    finally:
        sandbox.revoke(workspace, sid)
        try:
            workspace.rmdir()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm:
        print("refusing to change ACLs without --confirm", file=sys.stderr)
        return 2
    if not sandbox.supported():
        print(json.dumps({"supported": False, "reason": "windows_only"}))
        return 2

    sid = sandbox.ensure_profile()
    if args.revoke:
        for root in runtime_roots():
            sandbox.revoke(root, sid)
        print(json.dumps({"revoked": [str(root) for root in runtime_roots()]}))
        return 0

    granted = [] if args.verify_only else grant_runtime(sid)
    report = verify()
    print(
        json.dumps(
            {"sid": sid, "granted": [str(path) for path in granted], "verify": report},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
