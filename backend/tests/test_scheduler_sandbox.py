"""Scheduler wiring for the AppContainer launch path.

The container itself is verified by ``tools/sandbox_probe.py`` (attack matrix) and
locally by running ``cmd.exe`` through ``sandbox.popen``. These tests cover the
part that would otherwise silently regress: which command, cwd and environment
the scheduler hands to the sandbox.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.runtime.agent import scheduler as scheduler_module


def make_scheduler(tmp_path: Path):
    return scheduler_module.AgentScheduler(
        factory=None,
        owner="owner-1",
        cli_command=["python", "-m", "app.runtime.agent.cli", "--warm"],
    )


def staged_root(tmp_path: Path) -> Path:
    root = tmp_path / "agent-runtime"
    (root / "venv" / "Scripts").mkdir(parents=True)
    (root / "venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / "backend" / "app").mkdir(parents=True)
    return root


@pytest.mark.asyncio
async def test_container_launch_uses_staged_runtime_only(tmp_path, monkeypatch):
    root = staged_root(tmp_path)
    captured: dict = {}

    async def fake_popen(command, *, cwd, env=None, profile=None):
        captured.update(command=command, cwd=cwd, env=env)
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(scheduler_module.sandbox, "popen", fake_popen)
    settings = SimpleNamespace(
        agent_sandbox="appcontainer",
        agent_sandbox_runtime=str(root),
        agent_cli_module="app.runtime.agent.cli",
    )

    process = await make_scheduler(tmp_path)._spawn_in_container(settings)

    assert process.pid == 4242
    assert captured["command"][0] == str(root / "venv" / "Scripts" / "python.exe")
    assert captured["command"][1:] == ["-m", "app.runtime.agent.cli", "--warm"]
    assert captured["cwd"] == root / "backend"
    assert captured["env"] == {
        "PYTHONPATH": str(root / "backend"),
        "PYTHONUNBUFFERED": "1",
    }


@pytest.mark.asyncio
async def test_container_launch_refuses_without_runtime():
    settings = SimpleNamespace(
        agent_sandbox="appcontainer", agent_sandbox_runtime="", agent_cli_module="cli"
    )
    with pytest.raises(RuntimeError, match="AGENT_SANDBOX_RUNTIME"):
        await make_scheduler(Path("."))._spawn_in_container(settings)


@pytest.mark.asyncio
async def test_container_launch_refuses_incomplete_runtime(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    settings = SimpleNamespace(
        agent_sandbox="appcontainer", agent_sandbox_runtime=str(root), agent_cli_module="cli"
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        await make_scheduler(tmp_path)._spawn_in_container(settings)


def test_sandbox_env_carries_no_credentials():
    settings = SimpleNamespace(agent_sandbox_runtime=r"C:\runtime")
    env = scheduler_module._sandbox_cli_env(settings)
    assert "AI_API_KEY" not in env
    assert "PATH" not in env  # inherited from the whitelist, not the host env
    assert env["PYTHONPATH"].endswith("backend")
