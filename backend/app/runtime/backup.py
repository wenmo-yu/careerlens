"""Consistent local database backups (M2 leftover: backup/migration drill).

The desktop deployment uses SQLite. Copying the file while the API is writing is
not safe, so backups go through ``VACUUM INTO``, which produces a consistent
snapshot in one statement. ``verify`` then reopens the copy and checks both
integrity and that the Alembic version row survived.

PostgreSQL deployments are out of scope on purpose: a half-implemented
``pg_dump`` wrapper that silently produces an unusable dump is worse than a
clear refusal. Use the managed snapshot or ``pg_dump`` there.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


class BackupError(RuntimeError):
    """Backup refused or produced an unusable artifact."""


def sqlite_path(database_url: str) -> Path:
    """Extract the file path from a SQLAlchemy SQLite URL."""

    prefix = "sqlite+aiosqlite:///"
    plain = "sqlite:///"
    if database_url.startswith(prefix):
        raw = database_url[len(prefix) :]
    elif database_url.startswith(plain):
        raw = database_url[len(plain) :]
    else:
        raise BackupError(
            "only sqlite URLs are supported locally; use pg_dump or a managed "
            "snapshot for PostgreSQL"
        )
    if raw in {"", ":memory:"}:
        raise BackupError("in-memory databases cannot be backed up")
    return Path(raw)


def backup(database_url: str, out_dir: Path, *, stamp: datetime | None = None) -> Path:
    """Write a consistent copy into ``out_dir`` and return its path."""

    source = sqlite_path(database_url)
    if not source.exists():
        raise BackupError(f"database file not found: {source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    moment = (stamp or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"careerlens-{source.stem}-{moment}.db"
    if target.exists():
        raise BackupError(f"refusing to overwrite existing backup: {target}")

    # VACUUM INTO quotes the target itself, so bind it as a parameter.
    with sqlite3.connect(source) as connection:
        connection.execute("VACUUM INTO ?", (str(target),))
    report = verify(target)
    if not report["ok"]:
        target.unlink(missing_ok=True)
        raise BackupError(f"backup failed verification: {report['detail']}")
    return target


def verify(path: Path) -> dict:
    """Reopen a backup and report integrity plus migration state."""

    if not path.exists():
        return {"ok": False, "detail": "file missing", "path": str(path)}
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                return {
                    "ok": False,
                    "detail": f"integrity_check={integrity[0] if integrity else 'none'}",
                    "path": str(path),
                }
            tables = {
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type='table'"
                )
            }
            revision = None
            if "alembic_version" in tables:
                found = connection.execute("select version_num from alembic_version").fetchone()
                revision = found[0] if found else None
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "detail": f"not a usable database: {exc}", "path": str(path)}

    return {
        "ok": True,
        "detail": "integrity ok",
        "path": str(path),
        "tables": len(tables),
        "revision": revision,
        "bytes": path.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up and verify the local database.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy URL (sqlite only)")
    parser.add_argument("--out", default="backups", help="directory for the snapshot")
    parser.add_argument("--verify", default=None, help="verify an existing backup and exit")
    args = parser.parse_args(argv)

    if args.verify:
        report = verify(Path(args.verify))
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 1

    if not args.database_url:
        parser.error("--database-url is required unless --verify is used")
    try:
        target = backup(args.database_url, Path(args.out))
    except BackupError as exc:
        print(f"backup refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(verify(target), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
