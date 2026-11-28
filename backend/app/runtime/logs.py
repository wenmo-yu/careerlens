"""Rotating file logs for the long-running local processes.

The desktop host runs the API, the worker and the scheduler for days. Without
rotation their logs either grow without bound or disappear entirely once the
console buffer rolls over. This module keeps one rotating file per process and
stays idempotent: calling it twice (tests, restarts, double imports) does not
stack handlers or duplicate lines.

``LOG_DIR`` empty means "stdout only", which is what CI and unit tests want.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

TAG = "careerlens_process"
FORMAT = "%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s"


def configure(process: str, settings: Any = None) -> Path | None:
    """Attach a rotating handler for ``process``; return the file path used."""

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    level_name = str(getattr(settings, "log_level", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    directory = str(getattr(settings, "log_dir", "") or "").strip()
    root = logging.getLogger()
    root.setLevel(level)

    # Remove a previous handler for this process so repeated calls are safe.
    for handler in list(root.handlers):
        if getattr(handler, TAG, None) == process:
            root.removeHandler(handler)
            handler.close()

    if not directory:
        if not any(isinstance(item, logging.StreamHandler) for item in root.handlers):
            root.addHandler(logging.StreamHandler())
        return None

    target = Path(directory)
    try:
        target.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            target / f"{process}.log",
            maxBytes=max(0, int(getattr(settings, "log_max_bytes", 5 * 1024 * 1024))),
            backupCount=max(1, int(getattr(settings, "log_backups", 3))),
            encoding="utf-8",
        )
    except OSError:
        # Read-only containers (compose sets `read_only: true` on the worker) and
        # permission-restricted installs must not crash on startup just because
        # file logging is unavailable. Fall back to stdout and say so once.
        logging.getLogger(__name__).warning(
            "log directory %s is not writable; falling back to stdout", target
        )
        if not any(isinstance(item, logging.StreamHandler) for item in root.handlers):
            root.addHandler(logging.StreamHandler())
        return None

    handler.setFormatter(logging.Formatter(FORMAT))
    setattr(handler, TAG, process)
    root.addHandler(handler)
    return target / f"{process}.log"
