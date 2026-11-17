# Changelog

All notable changes to CareerLens are documented here.

## Unreleased

### Fixed

- Restored the `backend/app/models/` ORM package, which a bare `models/` rule in `.gitignore` had silently excluded from the repository. Fresh clones can now import `app.models` and run the test suite (was: collection error).
- Fixed `hybrid_search` pairing each returned `content` with a loop-leftover record instead of its own `evidence_id`, which silently corrupted local retrieval and evaluation results.
- Approval of a profile update now commits the correction evidence, profile changes, and proposal status in a single transaction; a mid-approval failure can no longer leave orphan evidence behind.
- `/health/ready` now returns HTTP 503 with `status: degraded` when a dependency is unavailable, so orchestrators can stop routing traffic to unhealthy instances.
- Backend Dockerfile now uses a two-stage uv build with `uv sync --frozen` against `uv.lock`, making dependency versions reproducible and allowing the `observability` extra (plus existing `ml`/`multimodal`) to be installed via build args.

### Added

- Multi-turn conversations: `ConversationMessage` persistence with an Alembic migration, prior-turn context assembly into the generation input, and full history returned in the chat response and rendered by the frontend workbench.
- `manage`-scoped authorization for instance-wide evaluation and observability endpoints in `required` auth mode (open in `disabled`/`optional` for local demos).

## 0.1.0 - 2026-10-16

### Added

- Evidence ingestion for text, documents, authorized Bilibili/Weibo exports, images, audio, and video.
- Evidence-grounded structured profiles, user-approved long-term memory updates, JD matching, skill gaps, learning paths, career reports, and LangGraph chat.
- PostgreSQL persistence, Alembic migrations, Qdrant hybrid retrieval, model and retrieval provider abstractions, and PostgreSQL checkpoints.
- DeepSeek/OpenAI-compatible and local Qwen routes with deterministic fallbacks.
- Authenticated MCP stdio/Streamable HTTP server, scoped access tokens, audit records, privacy export, and account deletion.
- Evaluation datasets, regression gates, model observability, OpenTelemetry integration, and GitHub Actions quality checks.
- Next.js workbench, Docker Compose deployment, production configuration template, service health checks, and disposable full-stack smoke tests.
