"""Verify the merged production Compose config enforces the security baseline.

Run against `docker compose -f docker-compose.yml -f docker-compose.production.yml
config --format json`, with synthetic secrets in the environment. The script
reads stdin so secrets never appear in command lines or CI logs.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid compose JSON: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    services = config.get("services", {})

    # Data stores must never publish host ports in production.
    for name in ("postgres", "qdrant"):
        service = services.get(name, {})
        if service.get("ports"):
            failures.append(f"{name} publishes host ports: {service['ports']}")

    # Public entry points bind to loopback only.
    for name in ("api", "mcp", "web"):
        service = services.get(name, {})
        for port in service.get("ports", []):
            host_ip = str(port.get("host_ip", ""))
            if host_ip not in {"127.0.0.1", "::1"}:
                failures.append(f"{name} port {port} is not loopback-only")

    # Authentication on, registration and metrics off by default.
    for name in ("api", "worker", "mcp"):
        env = services.get(name, {}).get("environment", {})
        if env.get("APP_ENV") != "production":
            failures.append(f"{name} APP_ENV is not production")
        if env.get("AUTH_MODE") != "required":
            failures.append(f"{name} AUTH_MODE is not required")
    api_env = services.get("api", {}).get("environment", {})
    if api_env.get("AUTH_REGISTRATION_ENABLED") not in (None, "false", False):
        failures.append("registration is not disabled by default")
    if api_env.get("METRICS_ENABLED") not in (None, "false", False):
        failures.append("metrics scrape is not disabled by default")
    if services.get("mcp", {}).get("environment", {}).get("MCP_AUTH_MODE") != "required":
        failures.append("MCP_AUTH_MODE is not required")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    print("production compose security baseline OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
