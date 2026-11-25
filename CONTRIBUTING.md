# Contributing

## Local checks

Use Python 3.11+ and Node.js 22+. Read the [roadmap](ROADMAP.md) for priorities and file
bugs or features using the repository's Issue forms. Use English or Chinese. For larger changes,
agree on an issue's scope and acceptance criteria before submitting a PR.

Install and verify the project before opening a pull request:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
Push-Location backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m app.evaluation.cli --dataset app/evaluation/dev_benchmark_v3.json --baseline ../eval/baselines/careerlens-dev-benchmark-v3.json
Pop-Location

Set-Location frontend
corepack enable
pnpm install --frozen-lockfile
pnpm lint
pnpm test
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
Follow the [code of conduct](CODE_OF_CONDUCT.md) and use the [security policy](SECURITY.md) for vulnerabilities.

## Branching and pull requests

We use a trunk-based flow with short-lived branches and pull requests:

1. Branch from `main` with a scoped prefix: `feat/`, `fix/`, `chore/`, or `docs/` (for example `feat/wiki-compile`).
2. Push the branch and open a pull request against `main`. The **Quality Gate** workflow runs on every PR: backend ruff + pytest + frozen regression gate, frontend lint + build + browser-helper tests, and a Docker full-stack smoke test. All checks must pass.
3. Keep one logical change per PR. Add or update tests for behavior changes, and update docs/CHANGELOG when user-facing behavior changes.
4. Merge with **Squash and merge** so `main` stays linear and readable. Delete the branch after merge — release tags, not long-lived branches, are how we preserve history.

> Direct pushes to `main` are reserved for release bookkeeping (version bumps, tag preparation). Feature work goes through PRs.

Maintainers: configure a ruleset on `main` requiring a pull request and the **backend-quality**,
**frontend-quality**, and **docker-smoke** checks. Leave required approvals at zero if there is
only one maintainer, but do not merge red or missing checks. Block force pushes and branch
deletion. Use **Automatically delete head branches** after merging. Include migration notes and
any tests that still require a live model in the PR.

## Versioning and releases

CareerLens follows [Semantic Versioning](https://semver.org/) while in `0.x` (no stable public API guaranteed yet):

- **Patch** (`0.2.1`): bug fixes that do not change behavior contracts.
- **Minor** (`0.3.0`): planned iteration milestones and backward-compatible features (e.g. the LLM Wiki iteration).
- **Major** (`1.0.0`): reserved for the first stable release with a documented compatibility promise.

Each iteration milestone is published as an annotated tag:

```bash
git tag -a v0.3.0 -m "CareerLens 0.3.0"
git push origin v0.3.0
```

Create the tag from the validated remote `main` commit. If a local tag with that name already
exists, verify that it points at the intended commit before pushing; never overwrite a remote
release tag to repair a stale local one.

Pushing a `v*` tag triggers the **Release** workflow, which extracts the matching version section from `CHANGELOG.md` and creates a GitHub Release automatically. Before tagging:

1. Move the relevant items out of `CHANGELOG.md`'s `Unreleased` section into a new `## <version> - YYYY-MM-DD` section.
2. Bump the version in `backend/pyproject.toml`, `backend/uv.lock` (the `careerlens-backend` package entry), and `frontend/package.json`. The FastAPI runtime version is read from `pyproject.toml`, so no code change is needed.

## Keeping the repository clean

Merged branches are deleted (locally and on the remote) after a PR closes; `main` plus release tags are the durable history. If you are cleaning up branches, verify a branch is fully merged first:

```bash
git branch --merged main        # safe to delete these
git push origin --delete <branch>
```
