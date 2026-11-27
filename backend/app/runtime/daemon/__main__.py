"""Entry point: `python -m app.runtime.daemon --api-exe <path>`."""

from __future__ import annotations

import argparse

from .lifecycle import DaemonConfig, run_daemon


def main() -> int:
    parser = argparse.ArgumentParser(description="CareerLens user-level daemon")
    parser.add_argument("--api-exe", required=True, help="packaged backend executable")
    parser.add_argument("--pipe", default=None, help="override the control pipe name")
    parser.add_argument("--health-url", default=None, help="override the health endpoint")
    args = parser.parse_args()

    overrides: dict[str, str] = {}
    if args.pipe:
        overrides["pipe_name"] = args.pipe
    if args.health_url:
        overrides["health_url"] = args.health_url
    return run_daemon(DaemonConfig(api_exe=args.api_exe, **overrides))


if __name__ == "__main__":
    raise SystemExit(main())
