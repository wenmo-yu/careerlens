"""Stage a container-readable agent runtime under %LOCALAPPDATA%.

Why: the container cannot traverse ``D:/work``, and writing a DACL on a tree that
large makes Windows propagate ACEs for minutes. Copying the runtime to a root
whose ancestors the AppContainer can already traverse avoids both problems and
matches what an installer would do anyway.

Layout::

    %LOCALAPPDATA%/CareerLens/agent-runtime/
        venv/            # fresh venv + site-packages copied from the dev venv
        backend/         # app package + pyproject.toml

Usage::

    python tools/sandbox_stage.py --confirm
    python tools/sandbox_stage.py --confirm --verify-only

Granting read/execute on the staged tree is a one-time cost (~12k files). The
script verifies by importing the CLI *inside* the container over pipes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.runtime import sandbox  # noqa: E402

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "tests", ".ruff_cache")


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CareerLens" / "agent-runtime"


def stage(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    venv = root / "venv"
    backend_copy = root / "backend"

    if not (venv / "Scripts" / "python.exe").exists():
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv)],
            check=True,
            capture_output=True,
        )
    target_site = venv / "Lib" / "site-packages"
    source_site = Path(sys.prefix) / "Lib" / "site-packages"
    if target_site.exists():
        # Rename instead of delete: a 12k-file rmtree trips the host's
        # safe-delete guard and is slow; a rename is instant and reversible.
        target_site.replace(target_site.with_name(f"site-packages.previous-{int(time.time())}"))
    shutil.copytree(source_site, target_site)

    if backend_copy.exists():
        backend_copy.replace(backend_copy.with_name(f"backend.previous-{int(time.time())}"))
    backend_copy.mkdir()
    shutil.copytree(BACKEND / "app", backend_copy / "app", ignore=IGNORE)
    shutil.copy2(BACKEND / "pyproject.toml", backend_copy / "pyproject.toml")
    return {"root": str(root), "venv": str(venv), "backend": str(backend_copy)}


def verify(staged: dict) -> dict:
    import asyncio

    venv_python = Path(staged["venv"]) / "Scripts" / "python.exe"
    backend_dir = Path(staged["backend"])
    sid = sandbox.ensure_profile()
    for path in (Path(staged["venv"]), backend_dir):
        if not sandbox.has_grant(path, sid):
            sandbox.grant(path, sid, permissions="(OI)(CI)(RX)")

    async def run() -> dict:
        proc = await sandbox.popen(
            [
                str(venv_python),
                "-c",
                "import app.runtime.agent.cli as m; print('staged-ok', m.__name__)",
            ],
            cwd=backend_dir,
            env={"PYTHONPATH": str(backend_dir)},
        )
        out = await asyncio.wait_for(proc.stdout.read(), timeout=180)
        err = await asyncio.wait_for(proc.stderr.read(), timeout=180)
        code = await asyncio.wait_for(proc.wait(), timeout=180)
        proc.close()
        return {
            "ok": code == 0 and b"staged-ok" in out,
            "exit_code": code,
            "stdout": out.decode("utf-8", "replace")[:400],
            "stderr": err.decode("utf-8", "replace")[-800:],
        }

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--root", default=None)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm:
        print("refusing to copy/stage without --confirm", file=sys.stderr)
        return 2
    if not sandbox.supported():
        print(json.dumps({"supported": False, "reason": "windows_only"}))
        return 2

    root = Path(args.root) if args.root else default_root()
    staged = (
        {"root": str(root), "venv": str(root / "venv"), "backend": str(root / "backend")}
        if args.verify_only
        else stage(root)
    )
    report = verify(staged)
    print(json.dumps({"staged": staged, "verify": report}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
