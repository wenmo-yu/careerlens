"""Local backup and log rotation: consistent snapshots, bounded log files."""

import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.runtime import backup, logs


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("create table alembic_version (version_num varchar(32))")
        connection.execute("insert into alembic_version values ('head-abc')")
        connection.execute("create table agent_runs (id text primary key, status text)")
        connection.execute("insert into agent_runs values ('r1', 'succeeded')")
        connection.commit()


def test_backup_is_consistent_and_verifiable(tmp_path):
    source = tmp_path / "career.db"
    make_database(source)
    target = backup.backup(f"sqlite+aiosqlite:///{source.as_posix()}", tmp_path / "backups")
    assert target.exists()
    report = backup.verify(target)
    assert report["ok"] is True
    assert report["revision"] == "head-abc"
    assert report["tables"] == 2  # alembic_version + agent_runs


def test_backup_refuses_memory_and_foreign_schemes(tmp_path):
    with pytest.raises(backup.BackupError):
        backup.backup("sqlite+aiosqlite:///:memory:", tmp_path)
    with pytest.raises(backup.BackupError) as exc:
        backup.backup("postgresql+asyncpg://user:pw@localhost/career", tmp_path)
    assert "pg_dump" in str(exc.value)


def test_backup_refuses_missing_source(tmp_path):
    with pytest.raises(backup.BackupError):
        backup.backup(f"sqlite:///{(tmp_path / 'absent.db').as_posix()}", tmp_path)


def test_verify_rejects_a_non_database(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("not a database", encoding="utf-8")
    report = backup.verify(junk)
    assert report["ok"] is False


def test_cli_returns_nonzero_on_refusal(tmp_path, capsys):
    assert backup.main(["--database-url", "postgresql://x/y", "--out", str(tmp_path)]) == 2
    assert "refused" in capsys.readouterr().err


def test_cli_backup_then_verify(tmp_path, capsys):
    source = tmp_path / "career.db"
    make_database(source)
    out = tmp_path / "out"
    assert backup.main(["--database-url", f"sqlite:///{source.as_posix()}", "--out", str(out)]) == 0
    created = next(out.glob("careerlens-*.db"))
    assert backup.main(["--verify", str(created)]) == 0
    assert '"ok": true' in capsys.readouterr().out


def settings_for(tmp_path, **overrides):
    values = {
        "log_dir": str(tmp_path / "logs"),
        "log_level": "INFO",
        "log_max_bytes": 4096,
        "log_backups": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_logs_rotate_and_stay_idempotent(tmp_path):
    settings = settings_for(tmp_path)
    path = logs.configure("worker", settings)
    assert path is not None and path.exists()
    # Reconfiguring must not stack handlers.
    logs.configure("worker", settings)
    file_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, logs.TAG, None) == "worker"
    ]
    assert len(file_handlers) == 1

    logger = logging.getLogger("rotation-probe")
    for index in range(400):
        logger.info("line %s %s", index, "x" * 40)
    for handler in file_handlers:
        handler.flush()
    rotated = list((tmp_path / "logs").glob("worker.log*"))
    assert len(rotated) >= 2, "expected the file to roll over at least once"
    for handler in list(logging.getLogger().handlers):
        if getattr(handler, logs.TAG, None) == "worker":
            logging.getLogger().removeHandler(handler)
            handler.close()


def test_empty_log_dir_means_stdout_only(tmp_path):
    assert logs.configure("scheduler", settings_for(tmp_path, log_dir="")) is None
    assert logs.configure("scheduler", settings_for(tmp_path, log_dir="  ")) is None


def test_unwritable_log_dir_falls_back_to_stdout(tmp_path, monkeypatch):
    """Read-only containers must keep running, not crash on file logging."""

    def refuse(*args, **kwargs):
        raise PermissionError(13, "read-only file system")

    monkeypatch.setattr(Path, "mkdir", refuse)
    assert logs.configure("worker", settings_for(tmp_path)) is None
    assert any(
        isinstance(handler, logging.StreamHandler)
        for handler in logging.getLogger().handlers
    )
