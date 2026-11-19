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
