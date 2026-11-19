# Changelog

All notable changes to CareerLens are documented here.

## Unreleased

## 0.4.0 - 2026-11-19

Runtime release: long-running work moves off the request thread into a durable,
resumable background worker with a live task center in the workbench.

### Added

- Durable background runs for document/media import, Wiki compilation, job analysis, and career reports. The workbench supports progress replay, approval, cancellation, and opening saved results.
- A PostgreSQL-backed Worker with per-user serialization, idempotency, lease recovery, revision fencing, and structured specialist workflows; no Redis is required.
- A transactional evidence index outbox retries Qdrant writes and deletes without blocking successful database ingestion.
- Open-source maintenance setup: ROADMAP, Code of Conduct, Issue/PR templates, dependabot, and a Docker double-worker smoke job in the quality gate.

### Fixed

- Production build: SSE progress decoding now uses a manual `TextDecoder` instead of `TextDecoderStream`, which no longer type-checks under TypeScript's stricter `Uint8Array<ArrayBufferLike>` generic. `pnpm build` succeeds again.
- Job matching and learning-plan computation: priority labels stay local to each JD clause, `weekly_hours` is validated, and required work is scheduled before optional gaps.

## 0.3.0 - 2026-11-18

Knowledge organization release: compiled, versioned Wiki pages with query-time
mode switching and configurable model roles.

### Added

- Versioned Wiki pages compiled from evidence (`POST /api/v1/wiki/compile`). Content and citation changes bump the version; link bookkeeping does not. Rollback restores content and citations as a new version, and machine revisions are pruned before human ones.
- Short-handle citation mapping: the compiler presents `c000`-style handles to the model and resolves them back to stable evidence ids before persisting; unknown handles are dropped and inline markers stripped from page Markdown.
- Table row-identity guard: rewrites that silently drop source table rows are rejected at the single page-write path, instead of being persisted unnoticed.
- Query-time mode switching: `ChatRequest.mode = rag | wiki | hybrid` — build once (RAG index / Wiki page / both), then switch without rebuilding. Hybrid interleaves ranked RAG and Wiki hits without comparing incompatible scores. The workbench can compile selected evidence, switch modes, and open cited Wiki pages.
- Role-bound LLM providers via `MODEL_ROLE_BINDINGS` (answer/wiki/analysis/profile) and a two-stage cascading reranker (`RERANK_STAGES_ENABLED`, coarse top-15 → fine top-5) with lexical degradation on stage failure. Both are CareerLens's own designs, not copied from WorkBuddy or WeKnora.

### Fixed

- Answer composition now handles Wiki hits (which carry `page_id`/`slug`) as well as RAG hits (`evidence_id`); previously a Wiki citation could raise a key error in the fallback answer and the model citation allow-set.
- Wiki writes reject concurrent changes and unavailable evidence. Deleting a source removes affected Wiki pages or revisions and linked parsed blocks. Qdrant hits are checked against live database evidence.
- Uploads now persist source locations and stable evidence references. User-scoped deduplication also holds for concurrent inserts; profile approvals index only after committing.
- The cascade selects the fine top-k across the entire coarse shortlist. Both model-role and reranker settings are passed through Compose.
- Updated Next.js and its ESLint config to 16.4.5 for security fixes.
- Job scoring keeps priority labels local to each JD clause, makes missing required skills explicit, and schedules required work before optional gaps. Reports and Copilot no longer reuse outdated job analyses.

## 0.2.0 - 2026-11-18

A foundation release: robustness fixes plus a structure-aware ingestion layer,
source-level deduplication, and durable multi-turn context.

### Added

- Multi-turn conversations: `ConversationMessage` persistence with an Alembic migration, prior-turn context assembly into the generation input, and full history returned in the chat response and rendered by the frontend workbench.
- `manage`-scoped authorization for instance-wide evaluation and observability endpoints in `required` auth mode (open in `disabled`/`optional` for local demos).
- Structure-aware parsing contract (`ParsedDocument` / `ParsedBlock`) with durable `SourceDocument` records; PDF pages parsed with numbering and text/scanned classification (image-area heuristic), DOCX tables, CSV/TSV, and a widened upload whitelist. OCR keeps per-line boxes; ASR keeps segment timestamps.
- Source-level deduplication keyed on `user_id + content_hash`: re-uploading identical text reuses the evidence row and appends the new origin to `source_metadata["sources"]`, so duplicate uploads no longer inflate profile confidence.
- Remove suppression: a user-removed profile item is tombstoned and will not reappear on rebuild. Profile rebuild and confirmed corrections mark affected reports `is_stale`.
- Frontend document upload card (PDF / DOCX / TXT / MD / CSV) wired to the existing upload endpoint.

### Changed

- Backend Dockerfile now uses a two-stage uv build with `uv sync --frozen` against `uv.lock`, making dependency versions reproducible and allowing the `observability` extra (plus existing `ml`/`multimodal`) to be installed via build args.
- Report version allocation is now atomic: a `(user_id, version)` unique constraint plus bounded retry eliminates the `max(version)+1` race (migration renumbers any pre-existing duplicates).

### Fixed

- Restored the `backend/app/models/` ORM package, which a bare `models/` rule in `.gitignore` had silently excluded from the repository. Fresh clones can now import `app.models` and run the test suite (was: collection error).
- Fixed `hybrid_search` pairing each returned `content` with a loop-leftover record instead of its own `evidence_id`, which silently corrupted local retrieval and evaluation results.
- Approval of a profile update now commits the correction evidence, profile changes, and proposal status in a single transaction; a mid-approval failure can no longer leave orphan evidence behind.
- `/health/ready` now returns HTTP 503 with `status: degraded` when a dependency is unavailable, so orchestrators can stop routing traffic to unhealthy instances.

## 0.1.0 - 2026-10-16

### Added

- Evidence ingestion for text, documents, authorized Bilibili/Weibo exports, images, audio, and video.
- Evidence-grounded structured profiles, user-approved long-term memory updates, JD matching, skill gaps, learning paths, career reports, and LangGraph chat.
- PostgreSQL persistence, Alembic migrations, Qdrant hybrid retrieval, model and retrieval provider abstractions, and PostgreSQL checkpoints.
- DeepSeek/OpenAI-compatible and local Qwen routes with deterministic fallbacks.
- Authenticated MCP stdio/Streamable HTTP server, scoped access tokens, audit records, privacy export, and account deletion.
- Evaluation datasets, regression gates, model observability, OpenTelemetry integration, and GitHub Actions quality checks.
- Next.js workbench, Docker Compose deployment, production configuration template, service health checks, and disposable full-stack smoke tests.
