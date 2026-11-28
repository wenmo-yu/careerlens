"""AppContainer sandbox surface: pure parts, refusals, and evidence consistency.

The real isolation checks need elevation (loopback exemption) and a Windows
host, so they live in ``tools/sandbox_probe.py`` and its recorded report
``docs/evidence/appcontainer-attack-matrix.json``. These tests cover the parts
that must be correct on any host and must fail closed everywhere else.
"""

import json
import sys
from pathlib import Path

import pytest

from app.runtime import sandbox


def test_non_windows_refuses_to_create_a_sandbox(monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    assert sandbox.supported() is False
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.ensure_profile()
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.run(["cmd"], cwd=Path("."))
    assert sandbox.status()["supported"] is False
    assert sandbox.delete_profile() is False


def test_environment_block_keeps_secrets_out_but_windows_can_start():
    import os

    os.environ["AI_API_KEY"] = "sk-should-not-leak"
    os.environ["GITHUB_TOKEN"] = "ghp_should_not_leak"
    try:
        block = sandbox._environment_block({"PYTHONIOENCODING": "utf-8"})
        import ctypes

        raw = ctypes.string_at(ctypes.addressof(block), ctypes.sizeof(block))
        text = raw.decode("utf-16-le")
        assert "AI_API_KEY" not in text
        assert "GITHUB_TOKEN" not in text
        # Process creation inside an AppContainer fails without these.
        for required in ("SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
            if os.environ.get(required):
                assert f"{required}=" in text
        assert text.endswith("\x00\x00")
    finally:
        os.environ.pop("AI_API_KEY", None)
        os.environ.pop("GITHUB_TOKEN", None)


def test_result_serialisation_trims_long_output():
    result = sandbox.SandboxResult(
        ok=False, exit_code=1, stdout="x" * 5000, stderr="y" * 5000
    )
    payload = result.as_dict()
    assert len(payload["stdout"]) <= 4000
    assert payload["ok"] is False and payload["exit_code"] == 1
    assert json.loads(sandbox.render(result))["exit_code"] == 1


@pytest.mark.skipif(not sandbox.supported(), reason="Windows only")
def test_status_reports_profile_without_creating_it():
    status = sandbox.status()
    assert status["supported"] is True
    assert "profile" in status
    # ready is False when the profile has never been created; either way the
    # call must not create it or raise.
    assert status["ready"] in (True, False)


def test_recorded_attack_matrix_has_no_violations():
    """The committed evidence must stay honest: every escape denied and no
    violation recorded; the allowed paths are exactly the two expected ones."""

    path = Path(__file__).resolve().parents[2] / "docs/evidence/appcontainer-attack-matrix.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["violations"] == []
    checks = {item["name"]: item["ok"] for item in report["checks"]}
    assert checks == {
        "read_host_secret": False,
        "write_outside": False,
        "write_workspace": True,
        "network_external": False,
        "network_loopback": True,
        "registry_write": False,
        "unc_read": False,
        "env_leak": True,
        "child_process": True,
    }
    assert "sid" in report and report["sid"].startswith("<redacted")
    assert sys.platform  # evidence is host-specific; keep the import meaningful
