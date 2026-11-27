# Changelog

All notable changes to CareerLens are documented here.

## Unreleased

### Security and reliability

- 分离租户、MCP 与实例运维权限。生产默认关闭注册和指标抓取，数据服务解除宿主机端口映射。新增令牌有效期、受众绑定、轮换窗口与可信运维签发。
- 跨存储清理任务在关系库事务中持久化。账号删除撤销访问，回执显示实际清理进度；删除证据后受影响的报告与会话内容被清理。
- 调整 Run 租约恢复、取消响应和并发约束。工作台以服务器会话身份隔离数据，支持有界 SSE 续看和提交结果未知时的幂等重试。
- Qdrant 候选先由 SQL 核对租户与现存记录，再重排。新索引校验模型指纹，换代提供维护窗口重建与 ID 对账。本地检索改用词法 RRF，报告真实重排诊断。
- 区分 Demo、模型失败和显式降级。岗位提取可保留逐字引文、资格与备选组，画像模型候选保留有效引文位置。
- 账号删除回执在没有外部向量集合时正确显示已完成，不再停在 unknown；被隐私清除标记的 Wiki 页不再进入检索结果。
- 首次对话允许调用方自带 thread_id：新线程在首轮创建，不再是 404；只有属于其他用户的线程才拒绝。
- Quality Gate 增加生产 Compose 合并配置校验：数据服务不映射宿主机端口、入口回环绑定、鉴权开启、注册与指标默认关闭。

画像与推荐增强（已进入主分支，待正式 Release）：

### Added

- V4 M3 持久 Agent 运行契约：`agent_sessions`/`agent_session_messages`/`agent_runtime_slots`/`agent_approvals` 与 `agent_runs.executor_kind, session_id`；ACK、settled、committed 三阶段分离，事件 seq 与 fencing token 同事务；每会话一个 CLI 进程，capability 限定到 user/session/run/attempt/generation；只读工具 `search_evidence`、`get_profile` 与流式模型网关。新增 39 项测试（含真实 CLI 子进程 + 桩网关），后端 344 passed，覆盖率 79.52%。见 `docs/adr/0010-m3-agent-runtime-contract.md`。
- V4 M4 Runtime Manager：预热池状态机（reserve 原子、绑定壳不回池、总进程上限）、两路并发准入、租约/fencing、旧代拒绝、崩溃退避补充与 `runtime/status`、`runtime/capabilities` 诊断；两个并发会话、6 个排队任务、崩溃重试、长任务超时均有测试。调度器入口要求 `AGENT_RUNTIME_ENABLED=true`，默认不启动。见 `docs/adr/0011-m4-runtime-manager.md`。
- V4 M2 第一步：daemon 从原型迁入 `backend/app/runtime/daemon/`（`contract` / `supervisor` / `control_ipc` / `lifecycle`），入口 `python -m app.runtime.daemon --api-exe <path>`；契约文件缺失时回退内置副本，新增 45 项 daemon 测试（41 项跨平台 + 4 项 Windows 专属）覆盖退避、熔断、握手、错误码与管道往返，后端覆盖率 78.65%；Quality Gate 增加 `daemon-windows` job。见 `docs/adr/0009-daemon-implementation-step-one.md`。
- V4 Daemon 协议：新增 `contracts/daemon-control-v1.json`，冻结本机管道控制面的握手、5 条命令与 6 个错误码，并在 daemon 原型上按契约实现；14 项端到端检查通过。见 `docs/adr/0008-daemon-control-protocol-v1.md`。
- V4 M1 原型：用户级 daemon 原型验证单实例锁、`KILL_ON_JOB_CLOSE` 进程组回收、API/Worker 监督与退避重启、按 SID 限定 DACL 的命名管道控制面；10 项端到端检查通过（含强杀 daemon 后无孤儿）。原型在仓库外，结论与未做项见 `docs/adr/0007-m1-daemon-supervision-prototype.md`。
- V4 打包事实：PyInstaller 冻结后 `sys.executable -m app.runtime.parse_input` 会退化成“重跑主程序”，PDF/DOCX 上传必然报 `Unable to parse this file`；需在入口分发解析子进程，并补 `--collect-all pymupdf`、`--collect-data docx`、`--add-data pyproject.toml`。补齐后 PDF/DOCX 解析与 `app.version=0.4.0` 在打包产物中验证通过，详见 ADR 0005。
- V4 M0 原型证据更新：打包产物上跑通完整业务链路（注册→证据→画像→chat→Run SSE，16 条事件，Run `succeeded`）与业务级审批两条路径；AppContainer 受限进程可启动，并观察到「宿主可写路径在容器内被拒、系统文件仍可读」的差异。单 exe 只跑 API 会让 Run 永远 `queued`，桌面启动器必须同时拉起 API 与 worker。见 `docs/adr/0005-m0-static-export-packaging-and-job-object.md`。
- V4 Runtime 契约：新增 `contracts/runtime-jsonl-v1.methods.json`，冻结 v1 五个方法与 11 个错误码（含可重试位、校验顺序、重复 id 上限），并在 `agent-runtime` 实现与测试，含旧代 `runtime_generation` 拒绝与事件种类/payload 必填校验；本机 23 项测试通过。见 `docs/adr/0006-runtime-jsonl-v1-method-registry.md`。
- V4 M0 原型：新增 `agent-runtime/` 自研 Agent Core 与 Runtime JSONL v1 双向 RPC 原型，用 ScriptedModel 验证模型→工具→回灌、审批屏障、取消和安全断点恢复；14 项本机测试通过，不接入真实模型、业务库或 OS 沙箱。结论见 `docs/adr/0004-m0-scripted-runner-prototype.md`，Quality Gate 增加对应 job。
- V4 M0 原型证据：Next.js 静态导出成功生成 7 个静态路由且资源引用齐全；最小 Tauri 2 宿主编译启动成功，WebView origin 为 `http://tauri.localhost`、16 个静态资源 200，跨源 API 需显式把该 origin 加入 CORS；PyInstaller onefile 后端入口能启动 uvicorn、返回 `/health/live` 200 并完成文本/文件基础解析；Windows Job Object 原型观察到进程数限制与关闭 job 终止子进程，AppContainer profile 可创建并删除。边界与未验证项见 `docs/adr/0005-m0-static-export-packaging-and-job-object.md`。
- 补充轮：三份带许可说明的本地量表（四维工作偏好 32 题、RIASEC 48 题、大五 20 题），题库为项目自写或仅参照公有领域构念，JSON 内记录未采用的 MBTI®/OEJTS/O*NET 等来源；确定性计分（80% 作答门槛、双极接近中点提示、RIASEC 代码一致性与分化度、大五反向题与分档），结果页给出方法说明与免责声明。
- 补充轮：`GET /assessments/instruments`、`GET /assessments/instruments/{id}`、`POST /assessments/instruments/{id}/submit`；画像概览新增 `assessments` 回显最近一次自陈结果，仍不进入事实画像与匹配分。
- 补充轮：GitHub 自备只读令牌导入（`POST /connectors/github/import`）：读仓库元数据与 README，令牌只在本次请求使用、不落库；注册表新增「自备只读令牌」等级并附最小权限创建教程。
- 补充轮：本地 HTML 另存为与用户导出 ZIP 解析（标准库实现，跳过 script/style、拒绝 ZIP 路径穿越）；连接器注册表按「用户导出 / 当前页采集 / 自备令牌 / 需授权」真实标注能力，OAuth 明确标为未实现；粘贴公开链接生成待确认证据卡，只保存用户所填文字、不访问链接。
- 补充轮：五种画像模式与模块开关（只改展示与软排序，不改事实/匹配分）、能力证据卡、证据锚定的面试故事库；浏览器当前页采集扩展到掘金/CSDN/知乎/小红书/GitHub，`authored/merged` 按用户自报处理、互动仍为兴趣线索；Run 事件渲染为带序号/耗时/代次/失败状态的步骤时间线。

- 前端工程补齐：`app/error.tsx`、`app/loading.tsx`、`app/not-found.tsx` 与站点图标；接口不可用时不再是白屏，404 有明确出口。
- 首页产品截图改为新版工作台真实渲染，不再是旧配色截图。
- `GET /metrics`：Prometheus 文本格式的请求计数、延迟直方图与并发数，标签用路由模板而不是原始 URL（避免每个用户 ID 生成一条序列）；`METRICS_ENABLED=false` 可关闭。
- Playwright 端到端测试：导入证据 → 画像 → 岗位匹配（走真实确认与 worker）→ 职业报告 → 下载入口，外加首页跳转与 404 页。
- 界面展示补齐 13 张真实局部截图（导入结果、证据回查、能力证据卡、画像模式、分数卡、学习看板、课程目录、职业方向、报告证据目录、Copilot 引用、测评、质量观测、数据控制）；截图脚本现在可复现全部 23 张文档图片。
- 依赖安全：`Dependency Audit` 工作流（pip-audit + pnpm audit），与质量门禁分开，新披露的 CVE 不会阻塞无关 PR；Dependabot 改为 pip/npm/actions 三生态并分组补丁升级。
- 后端测试覆盖率门槛：`pytest --cov --cov-fail-under=78`，当前 82%。
- Import Hub 结果卡：文件上传与媒体解析后显示可读条数、待 OCR 页数、重复跳过数、失败原因和可点击的证据定位；旧 `.doc` 返回转换提示；扫描页明确标注「任务成功不等于读出文字」。
- 粘贴文本与浏览器互动采用同一证据类型判断：只描述收藏/点赞/关注的语句标为 `preference_signal`，不会被抽取为技能事实。
- `GET /profiles/{id}/overview` 与 `GET /profiles/{id}/agent-manifest`：只读画像统计、证据覆盖度和机器可读的 Agent 能力清单；Agent 只能提案，不能静默写长期画像。
- 工作台画像可视化：五类分布、技能矩阵、证据时间线、覆盖度、报告八章全览和匹配分数拆解，全部提供文字表格降级，不引入图表库。
- 本地职业目录 `roles.json` 与课程目录 `courses.json`，配套只读 API 与确定性推荐；课程优先链接项目自己的教程，不使用外部付费数据源。
- 保存与对比 2–3 份 JD（`saved_jobs`）、学习看板与进度记录（`learning_progress`）；进度只能关联已存在的 Evidence，不产生新能力事实。
- 自陈测评：工作方式偏好、可选活动兴趣、自填人格标签；另有约束条件与自定义画像维度。结果单独存储、可跳过/重做/删除，不写入事实画像、不改变匹配分。
- 运行时新增 `profile_cartographer`、`role_scout`、`curriculum_planner` 三个只读 specialist；`Coordinator` 预算参数化，新增 `delegate_many` 用于无依赖角色的有限并行。

### Changed

- 前端视觉：先收敛为单一令牌层并修掉重复 `:root`，随后整体改为「暖纸 + 墨 + 赤陶」的印刷编辑风，替换掉默认靛蓝 SaaS 观感。`app/styles/tokens.css` 仍是唯一令牌源，新增 `--serif`（Noto Serif SC）只用于标题，正文与数字保持无衬线。中文标题字距 0、字号上限 60px、容器 1200px、圆角收到 4–13px。
- 标题层级改用衬线后，`h1–h4` 统一 `letter-spacing:0`；`h5` 与表单控件保持无衬线，避免数字和输入框失去节奏。
- 技能展示不再用「可信度百分比长度条」：改为 5 格等级刻度 + 可信度高/中/低分档 + 证据条数。原来所有条目都是 70%，条长完全一样，等于没有信息。
- 空状态从「＋ 加一句话」改为带下一步动作：无画像时跳到导入框、无报告时跳到岗位匹配、Copilot 空态可一键填入示例问题。
- 运行记录里的单个操作按钮不再被 `.report-actions button { flex:1 }` 拉成满宽横条。
- CSS 拆为 `tokens / base / shell / landing / workspace` 五层，`globals.css` 只做 `@import`；不再存在"后一段覆盖前一段"的双设计系统。
- 工作台从营销式 hero 改为工具头 + 五步流程条；section 间距从 100px 降到 40–56px；空状态合并为一块说明，不再堆四个占位框。
- 画像分布改为 SVG 雷达图，类别少于三类时自动降级为条形；技能与覆盖度增加状态色与百分比，`pill` 状态标签中文化；新增/修正 `confirmed / supported / weak / pending` 四个状态样式。
- 工作台状态与副作用抽到 `lib/use-workspace.ts`（32 个 state、26 个 handler），`app/workspace/page.tsx` 由 830 行降到 336 行，只保留渲染。
- Run 事件序号改为数据库层 `UPDATE ... RETURNING` 原子自增，避免并行进度写入重复 seq；`delegate()` 失败时补发 `step.failed` 终态事件，并记录 `duration_ms`。
- 所有本轮新表都纳入隐私导出与账号删除清单；测评与画像变更会把已有报告标为 stale。
- 本地职业目录新增 `riasec` 字段，用于兴趣结果的方向线索匹配；线索只说明兴趣重合，不代表能力或市场结论。
- 测评代码按领域拆分：`api/routes/assessment.py` 只保留测评结果（快测 + 三份量表 + 历史），约束/维度/画像模式/面试故事移到 `profile_extensions.py`；请求模型移到 `schemas/assessment.py`；旧快测与量表统一走 `services/assessment.py` 的 `record_assessment`，不再各写一套落库与 stale 逻辑。前端 `assessment-card.tsx` 拆为编排 + 快测 + 答题器 + 结果视图 + 约束维度五个文件。

### Fixed

- 后台上传完成后可在任务中心打开导入结果，查看可读证据、待 OCR 页数与原文。浏览器回归覆盖 HTML 上传。
- 面试故事使用独立编号，同一账号可保存多条同名故事。新增回归覆盖相同长标题。
- 公开链接证据卡与 GitHub 导入的确认复选框被 `.link-card-form input { min-width:170px }` 拉成 170px 宽，与说明文字分离；改为 `min-width:0` 的 15px 复选框。
- 刷新工作台时不恢复已保存画像，用户会误以为数据丢失；挂载时重新拉取 profile、overview 与 evidence。
- 同一用户在 1 秒内连续提交同一量表会撞 `(user_id, instrument, version, taken_at)` 唯一键并返回 500：`taken_at` 改为 Python 侧微秒时间戳，SQLite 的秒级 `CURRENT_TIMESTAMP` 不再造成碰撞；补回归用例。
- 镜像启动即崩：Dockerfile 用 `uv sync --frozen` 读 `backend/uv.lock`，而 `pyproject.toml` 新增了 `prometheus-client` 却未重新 lock，容器报 `ModuleNotFoundError`。已重新生成锁文件（仅新增 coverage / prometheus-client / pytest-cov）。
- `pip-audit` 同时使用 `--strict` 与 `--skip-editable` 会把这个项目自己当成错误并以退出码 1 结束，扫描根本没开始；去掉 `--strict`。
- pytest 8.4.2 命中 PYSEC-2026-1845（UNIX 上 `/tmp/pytest-of-{user}` 全局可写，本地 DoS 与可能的提权）；dev 依赖升到 `pytest>=9.0.3,<10` 与 `pytest-asyncio>=1.0,<2`。生产镜像用 `--no-dev`，运行时不引入 pytest。
- Dependabot 的 Python 生态指错：仓库有 `backend/uv.lock` 且镜像由 uv 构建，应使用 `uv` 而不是 `pip`。
- GitHub 仓库地址带 `?tab=readme` 或 `#install` 时被误判为非法 `owner/name`：规范化时先剥离 query 与 fragment。

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
