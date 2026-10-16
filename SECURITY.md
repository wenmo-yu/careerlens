# Security Policy

## Supported version

Only the latest commit on `main` receives security fixes while CareerLens is in active development.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting when it is enabled for the repository. Do not open a public issue containing API keys, access tokens, personal Evidence, database dumps, authentication bypass details, or working exploit payloads.

Include the affected component, reproduction conditions, expected impact, and a minimal proof of concept with all personal data and secrets removed.

## Deployment requirements

- Never commit `.env`, provider keys, database files, uploaded documents, model caches, or exported user data.
- For non-local deployments, use `docker-compose.production.yml`, set `AUTH_MODE=required`, and replace every example credential.
- Put HTTP services behind TLS and a trusted reverse proxy. Restrict PostgreSQL and Qdrant ports at the network boundary.
- Back up PostgreSQL and Qdrant together and test restoration and deletion propagation.
- Treat MCP stdio as a trusted local boundary. Expose only the authenticated Streamable HTTP transport remotely.
