# Security Policy

## Supported version

Only the latest commit on `main` receives security fixes while CareerLens is in active development.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/wenmo-yu/careerlens/security/advisories/new) when it is enabled. If unavailable, ask the maintainer for a private contact route without posting any details of the issue.

In a private report, include the affected version, component, expected impact, and suggested mitigation if known. Never include personal Evidence, database dumps, or credentials.

## Deployment requirements

- Never commit `.env`, provider keys, database files, uploaded documents, model caches, or exported user data.
- For non-local deployments, use `docker-compose.production.yml`, set `AUTH_MODE=required`, and replace every example credential.
- Put HTTP services behind TLS and a trusted reverse proxy. Restrict PostgreSQL and Qdrant ports at the network boundary.
- Back up PostgreSQL and Qdrant together and test restoration and deletion propagation.
- Treat MCP stdio as a trusted local boundary. Expose only the authenticated Streamable HTTP transport remotely.
- `GET /metrics` carries no personal data (request counts, latency histograms, in-flight gauge) and is unauthenticated like the probes. When the API is reachable from the internet, set `METRICS_ENABLED=false` or restrict the path at the gateway.

## Dependencies and supply chain

- `Dependency Audit` runs weekly, on manual dispatch, and whenever `backend/pyproject.toml`, `backend/uv.lock` or `frontend/pnpm-lock.yaml` change. It runs `pip-audit` over the installed backend environment and `pnpm audit --prod --audit-level high`.
- It is a separate workflow on purpose: a newly published CVE should fail that workflow immediately without blocking unrelated pull requests.
- Dependabot watches three ecosystems (uv at `/backend`, npm at `/frontend`, GitHub Actions at `/`). Patch updates are grouped into single PRs; major jumps on `langgraph` and `mcp` are ignored because they need a migration.
- The backend image builds with `uv sync --frozen` from `backend/uv.lock`. Changing dependencies in `pyproject.toml` without regenerating the lock produces an image missing packages, so both files must move together.
