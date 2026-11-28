"""M5 workspace file broker policy and idempotent writes."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.agent import AgentApproval, AgentToolLedger
from app.runtime.agent import file_broker, tools


def configure(monkeypatch, root, *, extensions=".txt,.md", max_bytes=1024):
    monkeypatch.setattr(
        file_broker,
        "get_settings",
        lambda: SimpleNamespace(
            agent_workspace_root=str(root),
            agent_file_allow_extensions=extensions,
            agent_file_max_bytes=max_bytes,
        ),
    )


async def _approval(session, *, args, user="u1", run="r1", invocation="call-1", status="approved"):
    record = AgentApproval(
        run_id=run,
        user_id=user,
        invocation_id=invocation,
        tool="write_workspace_file",
        args_digest=tools.digest_args(args),
        scope="workspace.write",
        status=status,
    )
    session.add(record)
    await session.flush()
    return record


async def _invoke(session, *, args, approval, user="u1", run="r1"):
    return await tools.invoke(
        session,
        user_id=user,
        name="write_workspace_file",
        args=args,
        run_id=run,
        session_id="s1",
        invocation_id=approval.invocation_id,
        approval_id=approval.id,
        approved=approval.status == "approved",
        args_digest=tools.digest_args(args),
    )


async def test_read_file_accepts_clean_relative_path(session_factory, tmp_path, monkeypatch):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.txt").write_text("证据内容", encoding="utf-8")
    configure(monkeypatch, tmp_path)
    async with session_factory.begin() as session:
        result = await tools.invoke(
            session, user_id="u1", name="read_workspace_file",
            args={"path": "notes/a.txt"}, run_id="r1",
        )
    assert result == {"path": "notes/a.txt", "content": "证据内容", "bytes": 12}


@pytest.mark.parametrize(
    "path,code",
    [
        ("../secret.txt", "path_denied"),
        ("/etc/passwd", "path_denied"),
        ("C:/Windows/win.ini", "path_denied"),
        ("//server/share/file.txt", "path_denied"),
        ("notes/a.txt:stream", "path_denied"),
        ("notes\\a.txt", "path_denied"),
        ("notes/./a.txt", "path_denied"),
        ("notes/a.exe", "extension_denied"),
        ("missing.txt", "file_not_found"),
    ],
)
async def test_read_file_denies_unsafe_paths(
    session_factory, tmp_path, monkeypatch, path, code
):
    configure(monkeypatch, tmp_path)
    async with session_factory.begin() as session:
        with pytest.raises(tools.ToolRejected) as exc:
            await tools.invoke(
                session, user_id="u1", name="read_workspace_file",
                args={"path": path}, run_id="r1",
            )
    assert exc.value.code == code


async def test_read_file_denies_symlink_escape(session_factory, tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(outside)
    except OSError as exc:
        outside.unlink(missing_ok=True)
        pytest.skip(f"symlink creation is not available on this host: {exc}")
    configure(monkeypatch, tmp_path)
    async with session_factory.begin() as session:
        with pytest.raises(tools.ToolRejected) as exc:
            await tools.invoke(
                session, user_id="u1", name="read_workspace_file",
                args={"path": "link.txt"}, run_id="r1",
            )
    assert exc.value.code == "path_denied"
    outside.unlink(missing_ok=True)


async def test_read_file_denies_oversized_file(session_factory, tmp_path, monkeypatch):
    (tmp_path / "big.txt").write_text("x" * 2000, encoding="utf-8")
    configure(monkeypatch, tmp_path, max_bytes=1024)
    async with session_factory.begin() as session:
        with pytest.raises(tools.ToolRejected) as exc:
            await tools.invoke(
                session, user_id="u1", name="read_workspace_file",
                args={"path": "big.txt"}, run_id="r1",
            )
    assert exc.value.code == "file_too_large"


async def test_write_file_requires_approval_and_is_idempotent(
    session_factory, tmp_path, monkeypatch
):
    configure(monkeypatch, tmp_path)
    args = {"path": "notes/a.md", "content": "第一条"}
    async with session_factory.begin() as session:
        with pytest.raises(tools.ToolRejected) as missing:
            await tools.invoke(
                session, user_id="u1", name="write_workspace_file",
                args=args, run_id="r1", invocation_id="call-1",
            )
        assert missing.value.code == "approval_required"
        approval = await _approval(session, args=args)
        first = await _invoke(session, args=args, approval=approval)
        second = await _invoke(session, args=args, approval=approval)
        ledger = list(await session.scalars(select(AgentToolLedger)))
    assert first == second
    assert first["overwritten"] is False
    assert len(ledger) == 1 and ledger[0].status == "succeeded"
    assert (tmp_path / "notes" / "a.md").read_text(encoding="utf-8") == "第一条"


async def test_write_file_digest_conflict_does_not_overwrite(
    session_factory, tmp_path, monkeypatch
):
    configure(monkeypatch, tmp_path)
    original = {"path": "a.txt", "content": "原文"}
    async with session_factory.begin() as session:
        approval = await _approval(session, args=original)
        await _invoke(session, args=original, approval=approval)
        with pytest.raises(tools.ToolRejected) as conflict:
            await tools.invoke(
                session,
                user_id="u1",
                name="write_workspace_file",
                args={"path": "a.txt", "content": "篡改"},
                run_id="r1",
                session_id="s1",
                invocation_id="call-1",
                approval_id=approval.id,
                approved=True,
                args_digest=tools.digest_args({"path": "a.txt", "content": "篡改"}),
            )
    assert conflict.value.code == "tool_ledger_conflict"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "原文"


async def test_write_file_denies_symlinked_parent(session_factory, tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside-dir"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        outside.rmdir()
        pytest.skip(f"symlink creation is not available on this host: {exc}")
    configure(monkeypatch, tmp_path)
    args = {"path": "escape/a.txt", "content": "x"}
    async with session_factory.begin() as session:
        approval = await _approval(session, args=args)
        with pytest.raises(tools.ToolRejected) as exc:
            await _invoke(session, args=args, approval=approval)
    assert exc.value.code == "path_denied"
    assert not (outside / "a.txt").exists()
    (tmp_path / "escape").unlink()
    outside.rmdir()
