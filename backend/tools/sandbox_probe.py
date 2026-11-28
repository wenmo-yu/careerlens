"""T14/T16 AppContainer attack matrix.

Runs a child process inside an AppContainer with no capabilities and checks that
the OS — not our application code — blocks the escapes we care about:

- read a secret outside the granted workspace          -> must fail
- write outside the granted workspace                  -> must fail
- write into the granted workspace                     -> must succeed
- outbound network to a public address                 -> must fail
- loopback to the local API                            -> must succeed
- HKCU registry write                                  -> must fail
- UNC / admin-share read                               -> must fail
- environment leak of a secret                         -> must be absent
- spawn a child process                                -> observed (Job Object owns
  spawn limits; AppContainer alone does not forbid it)

The child is PowerShell, not Python: ``%SystemRoot%\\System32`` is readable by an
AppContainer by default, so the probe needs no interpreter ACL grants and cannot
accidentally prove access we handed it ourselves.

Usage::

    python tools/sandbox_probe.py --confirm
    python tools/sandbox_probe.py --confirm --keep-profile --json-out report.json

It creates a per-user AppContainer profile (`careerlens-agent`), grants it
read/execute on a throwaway workspace plus a test secret, exempts loopback, runs
the probes, then removes the ACLs and (unless kept) the profile.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.runtime import sandbox  # noqa: E402

CHILD = r"""
$ErrorActionPreference = "Continue"
$secret = $args[0]
$workspace = $args[1]
$port = [int]$args[2]
$results = @()

function Add-Result([string]$name, [bool]$allowed, [string]$detail) {
    $script:results += [ordered]@{ name = $name; ok = $allowed; detail = $detail }
}

try {
    $text = Get-Content -LiteralPath $secret -Raw -ErrorAction Stop
    Add-Result "read_host_secret" $true "read $($text.Length) chars"
} catch { Add-Result "read_host_secret" $false $_.Exception.GetType().Name }

try {
    Set-Content -LiteralPath "$secret.escape" -Value "probe" -ErrorAction Stop
    Add-Result "write_outside" $true "wrote"
} catch { Add-Result "write_outside" $false $_.Exception.GetType().Name }

try {
    Set-Content -LiteralPath (Join-Path $workspace "probe-ok.txt") -Value "probe" -ErrorAction Stop
    Add-Result "write_workspace" $true "wrote"
} catch { Add-Result "write_workspace" $false $_.Exception.GetType().Name }

try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("1.1.1.1", 443)
    $client.Close()
    Add-Result "network_external" $true "connected"
} catch { Add-Result "network_external" $false $_.Exception.GetType().Name }

try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", $port)
    $client.Close()
    Add-Result "network_loopback" $true "connected"
} catch { Add-Result "network_loopback" $false $_.Exception.GetType().Name }

try {
    New-Item -Path "HKCU:\Software\CareerLensProbe" -Force -ErrorAction Stop | Out-Null
    New-ItemProperty -Path "HKCU:\Software\CareerLensProbe" -Name probe `
        -Value 1 -ErrorAction Stop | Out-Null
    Add-Result "registry_write" $true "wrote"
} catch { Add-Result "registry_write" $false $_.Exception.GetType().Name }

try {
    Get-Content -LiteralPath "\\127.0.0.1\C$\Windows\win.ini" -ErrorAction Stop | Out-Null
    Add-Result "unc_read" $true "read"
} catch { Add-Result "unc_read" $false $_.Exception.GetType().Name }

Add-Result "env_leak" (-not (Test-Path env:AI_API_KEY)) "AI_API_KEY checked"

try {
    $out = & "$env:SystemRoot\System32\cmd.exe" /c "echo ok" 2>&1
    Add-Result "child_process" $true ($out -join " ")
} catch { Add-Result "child_process" $false $_.Exception.GetType().Name }

ConvertTo-Json -InputObject $results -Compress
"""


def free_port() -> tuple[socket.socket, int]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    return listener, listener.getsockname()[1]


def serve_once(listener: socket.socket) -> None:
    def loop() -> None:
        try:
            connection, _ = listener.accept()
            connection.close()
        except OSError:
            pass

    threading.Thread(target=loop, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="required: creates a profile")
    parser.add_argument("--keep-profile", action="store_true")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    if not args.confirm:
        print("refusing to run without --confirm", file=sys.stderr)
        return 2
    if not sandbox.supported():
        print(json.dumps({"supported": False, "reason": "windows_only"}))
        return 2

    def step(message: str) -> None:
        print(f"[probe] {message}", file=sys.stderr, flush=True)

    sid = sandbox.ensure_profile()
    step(f"profile ready sid={sid[:24]}…")
    workspace = Path(tempfile.mkdtemp(prefix="careerlens-sandbox-"))
    secret = Path.home() / f".careerlens-probe-{workspace.name}.txt"
    secret.write_text("top-secret", encoding="utf-8")
    granted: list[Path] = []
    listener = None
    try:
        # Only the workspace and the test secret are granted. The interpreter is
        # never granted, so a passing probe cannot be an artefact of our own ACLs.
        # Modify (not read-only): the agent writes notes into its workspace.
        # Only the leaf is granted — granting ancestors makes icacls walk whole
        # trees (node_modules, package caches) and can take minutes.
        sandbox.grant(workspace, sid, permissions="(OI)(CI)(M)")
        step("workspace granted")
        # The secret is deliberately NOT granted: the probe must show the
        # default deny, not an ACL we added ourselves.
        sandbox.loopback_exempt(sid)
        step("loopback exempt")

        script = workspace / "probe.ps1"
        script.write_text(CHILD, encoding="utf-8")
        listener, port = free_port()
        serve_once(listener)

        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        step("launching child")
        result = sandbox.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                str(secret),
                str(workspace),
                str(port),
            ],
            cwd=workspace,
            timeout=90,
            profile=sandbox.PROFILE,
        )
        step(f"child exited code={result.exit_code} timed_out={result.timed_out}")
        raw = result.stdout.strip()
        checks = json.loads(raw) if raw.startswith(("{", "[")) else []
        if isinstance(checks, dict):
            checks = [checks]
        report = {
            "supported": True,
            "sid": sid,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stderr": result.stderr[-800:],
            "checks": checks,
        }
        expect_denied = {
            "read_host_secret",
            "write_outside",
            "network_external",
            "registry_write",
            "unc_read",
        }
        expect_allowed = {"write_workspace", "network_loopback"}
        violations = []
        for check in checks:
            name, allowed = check["name"], bool(check["ok"])
            if name in expect_denied and allowed:
                violations.append(f"{name} should have been denied")
            if name in expect_allowed and not allowed:
                violations.append(f"{name} should have been allowed: {check['detail']}")
            if name == "env_leak" and not allowed:
                violations.append("AI_API_KEY leaked into the sandbox environment")
        report["violations"] = violations
        report["passed"] = not violations and bool(checks)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return 0 if report["passed"] else 1
    finally:
        if listener is not None:
            listener.close()
        sandbox.revoke_chain(granted, sid)
        secret.unlink(missing_ok=True)
        sandbox.loopback_unexempt(sid)
        if not args.keep_profile:
            sandbox.delete_profile()
        for child in workspace.glob("*"):
            child.unlink(missing_ok=True)
        workspace.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
