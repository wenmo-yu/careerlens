# Contributing

## Local checks

Use Python 3.11+ and Node.js 22+. Install and verify the project before opening a pull request:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m pytest backend/tests -q

Set-Location frontend
corepack enable
pnpm install --frozen-lockfile
pnpm lint
pnpm build
```

For integration changes, start Docker and run the disposable full-stack smoke test:

```powershell
docker compose up -d --build
.\scripts\docker-smoke.ps1
```

## Data and security

Use synthetic or explicitly authorized, anonymized data in tests and examples. Never commit personal exports, resumes, cookies, API keys, access tokens, `.env` files, local databases, or model caches.

Keep pull requests focused and include tests for behavior changes. Database model changes require an Alembic revision.
