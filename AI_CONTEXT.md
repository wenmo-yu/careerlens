# CareerLens AI 上下文导航（AI 专用）

> 更新时间：2026-11-27。这个文件是给 AI 查阅用的代码与公开文档索引。
> 目标：让 AI 在回答「某个功能在哪、以前怎么做、现在怎么做、改它要读什么」时，不必重新遍历整个仓库。
> 入口规则见 [`AGENTS.md`](AGENTS.md)；仓库外的本地管理文档见 [`../AI查阅导航.md`](../AI查阅导航.md)。

---

## 0. 先看当前事实

| 维度 | 当前值 |
| --- | --- |
| 产品版本 | v0.4.0；三期产品交付完成，`CHANGELOG.md` 已回填 |
| 仓库 | https://github.com/wenmo-yu/careerlens |
| 公开教程站 | https://wenmo-yu.github.io/careerlens/ |
| 最新公开提交 | `ce5bb08`（PR #59，教程同步画像与岗位工作台）；本轮文档/截图提交 `34680ab` → `aee4487` → `9953471` |
| 验证基线 | 后端 258 项测试（覆盖率门槛 78%，实测 78.35%）、20 个冻结合成场景、Playwright 端到端 5 项、Quality Gate 四项与依赖审计两项全绿（backend / frontend / e2e / docker-smoke / pip-audit / pnpm audit）；Docsify build 111 文件 0 坏链，Pages 部署成功；源码整改后新增安全、跨存储删除、运行时不变量、检索世代与前端幂等等专项测试 |
| 默认可运行方式 | Docker Compose；无需 API Key，使用确定性 Demo 模型与本地检索 |
| 仍未完成 | 真人独立试学、真机初装/剪贴板/跨端点检、真实模型与旧库迁移；这些是验证缺口，不是源码缺口 |
| 本地 git 状态 | 本地 `HEAD` 和 `ahead` 可能滞后（远端 fetch 502），**远端 main + Actions + Pages 才是权威** |

**一句话**：产品代码已到 v0.4.0，画像与推荐增强批次已推送，教程已全章加厚并补上第 10/11 篇画像与岗位实战；AI 查代码时优先相信本文件、`CHANGELOG.md`、`docs/README.md` 和源码，不要相信早期草案或本地 git 指针。

---

## 1. 使用约定

### 1.1 真相优先级

从高到低：

1. **当前源码**与运行结果；
2. `CHANGELOG.md`（版本级权威变更记录）、`docs/README.md`（技术文档入口）、`README.md`（产品入口）；
3. `tutorials/`（公开教学材料，当前版本已按源码核对）；
4. 本地 `../CareerLens文档导航.md` 与 `../CareerLens教学项目台账/`（本地沟通真相源，不在仓库内）；
5. 三份验收报告（**当时快照**，不要改写其中数字）；
6. `../历史归档/` 与旧 commit（只用于追溯决策，不作为当前依据）。

### 1.2 不要读的目录

`.git/`、`.venv/`、`node_modules/`、`.next/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.cache/`、`*.egg-info/` 都是依赖或缓存，不是项目源码。

工作区根目录下的 `app.asar.extracted/`、`weknora-source/` 是外部参考材料，不属于 CareerLens 仓库；只有明确要求做实现对照时才读取。

### 1.3 前端框架例外

`frontend/AGENTS.md` 由 `next dev` 生成并维护，写 Next.js 代码时仍须遵守；需要确认框架 API 时读 `frontend/node_modules/next/dist/docs/`。这和本导航不冲突。

---

## 2. 工作区与仓库边界

```text
D:/work/career/                     本地工作区，不是 Git 仓库
├── CareerLens文档导航.md           管理文档真相源（当前状态、有效/归档分层）
├── AI查阅导航.md                   工作区级 AI 入口（本文件的上级）
├── CareerLens教学项目台账/          本地执行台账，不上传、不发布
├── 历史归档/                       早期草案与已完成方案，理解来龙去脉时才读
├── CareerLens三阶段迭代方案.md      产品三期蓝图与验收结论
├── CareerLens零基础教程体系方案.md  教程设计原理与写作方法
├── CareerLens教程思考题集.md / CareerLens面试问答_清理重写版.md
├── CareerLens第一/二/三期验收报告.md
└── careerlens/                    公开 GitHub 仓库（本文件所在）
```

**关键规则**：本地台账和历史归档不在产品 Git 工作树内。不要把它们复制到公开 Issue、PR 或 Pages。

---

## 3. 顶层目录总览

| 路径 | 放的是什么 | AI 什么时候读 |
| --- | --- | --- |
| `README.md` | 产品定位、快速开始、架构图、技术栈、验证摘要 | 第一次理解项目；不要在这里找接口细节 |
| `CHANGELOG.md` | v0.1→v0.4 版本变更与破坏性修复 | 判断「以前/现在」、某行为何时引入 |
| `ROADMAP.md` | 维护顺序和待环境验证项 | 判断哪些是计划、哪些已完成 |
| `CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` / `LICENSE` | 社区与法律文件 | 发布、贡献、安全相关任务 |
| `.env.example` / `.env.production.example` | 本地与生产配置模板 | 配置、模型、认证、部署问题 |
| `docker-compose*.yml` | 默认、生产、Qwen、多模态容器编排 | 启动、Worker 数量、端口、依赖服务 |
| `backend/` | FastAPI + SQLAlchemy + Alembic 后端 | 几乎所有业务机制 |
| `frontend/` | Next.js 工作台与公开页 | 界面、交互、SSE、截图 |
| `docs-site/` | Docsify 教程站壳、侧栏、构建脚本 | 改教程站、发布 Pages、链接/锚点 |
| `docs/` | 公开技术文档 | 架构、数据、Agent/检索、运维口径；`docs/adr/` 是 V4 决策记录 |
| `contracts/` | V4 版本化机器可读契约：OpenAPI 快照、API 基线、Runtime JSONL v1 | 改跨端/跨进程接口前先读；不要把 JSONL 日志当业务事实 |
| `agent-runtime/` | 自研 Agent Core M0 原型：ScriptedModel、内存端口、JSONL 双向 RPC | 只用于验证状态机/协议；不要当生产运行时或安全边界 |
| `tutorials/` | 零基础课程正文与练习 | 教学、概念解释、源码导读 |
| `examples/` | 跟做脚本和合成夹具 | 验证课程练习是否可复跑 |
| `eval/` | 评测数据集与基线 | 评测口径、回归基线 |
| `scripts/` | `docker-smoke.ps1` 全栈冒烟 | 本地验收、CI 复现 |
| `browser-helper/` | 浏览器采集扩展 | 授权采集流程、采集脚本 |
| `.github/` | Issue/PR 模板、dependabot、Actions | CI、发布、Pages、社区模板 |

---

## 4. backend/：业务源码地图

### 4.1 启动、配置、数据库

| 文件 | 放的是什么代码 |
| --- | --- |
| `backend/pyproject.toml` | 依赖、脚本、Ruff/pytest 配置、版本号；`main.py` 从这里读版本 |
| `backend/app/main.py` | FastAPI `create_app()`、CORS、健康检查、路由、应用级聊天图与 telemetry 生命周期；启动时校验生产配置 |
| `backend/app/migration_runner.py` | 启动时执行 Alembic 迁移的辅助逻辑 |
| `backend/app/core/config.py` | `get_settings()`：认证模式、API 前缀、CORS、模型、检索、运行时的全部配置入口 |
| `backend/app/core/database.py` | 异步 engine / session / `create_schema()` |
| `backend/app/api/router.py` | 所有 `/api/v1/*` 路由汇总：`auth/evidence/profiles/jobs/chat/connectors/observability/evaluation/reports/runs/privacy/wiki` |

### 4.2 API 路由（`backend/app/api/routes/`）

| 文件 | 放的是什么代码 |
| --- | --- |
| `auth.py` | 注册、令牌 scope、有效期/受众和 `/me` 身份入口。运维签发或恢复账号见 `backend/app/security/provision.py` |
| `health.py` | `/health` 与 `/health/ready`；依赖不可用时返回 503 + `degraded` |
| `evidence.py` | 证据导入、列表、来源、删除；上传文件与去重入口 |
| `profile.py` | 画像读取、重建、条目操作 |
| `jobs.py` | JD 分析入口 |
| `chat.py` | Copilot 同步对话入口，`rag/wiki/hybrid` 模式在这里进入 |
| `reports.py` | 报告生成、版本列表与下载 |
| `runs.py` | 后台 Run 提交、审批、取消、详情、事件/SSE 进度流 |
| `wiki.py` | Wiki 编译、页面读取、回滚、版本操作 |
| `connectors.py` | B站/微博导出与浏览器采集接入；画像推荐补充轮新增 `/connectors/registry`（来源清单）、`/connectors/public-link/import`（用户粘贴的证据卡，后端不访问 URL）与 `/connectors/github/import`（自备只读令牌，令牌不落库） |
| `privacy.py` | 导出、单条删除、账号清理 |
| `evaluation.py` | 评测运行与结果读取，鉴权部署使用实例运维凭证 |
| `observability.py` | 指标/追踪只读接口，鉴权部署使用实例运维凭证 |
| `catalog.py` | 画像推荐只读目录：`/catalog/roles`、`/catalog/courses` |
| `profile_extensions.py` | 自陈扩展入口：`/constraints/me`、`/profiles/{id}/dimensions`、`/profiles/{id}/view-preferences`（画像模式与模块开关）、`/profiles/{id}/interview-stories`（证据锚定故事库）。只改展示/过滤/软排序，不碰事实与匹配分 |
| `recommendations.py` | 画像推荐确定性推荐：`/recommendations/roles`、`/recommendations/learning-plan` |
| `learning.py` | 画像推荐：`/saved-jobs`（保存/对比 JD）、`/learning/plans/{id}/progress` |
| `assessment.py` | 自陈测评结果入口：旧版快测题与提交、三份量化表的清单/题目/提交、结果列表与删除。路由只做鉴权、参数校验和响应拼装，落库与 stale 标记统一走 `services/assessment.py` |

### 4.3 数据模型与契约

| 路径 | 放的是什么代码 |
| --- | --- |
| `backend/app/models/evidence.py` | `Evidence` ORM：稳定证据 ID、内容 hash、来源元数据 |
| `backend/app/models/source_document.py` | `SourceDocument`：原始上传/导入记录，保留来源位置 |
| `backend/app/models/parsed_block.py` | `ParsedBlock`：结构感知解析后的页、表、行、段落块 |
| `backend/app/models/profile.py` | 画像条目、置信度、证据引用 |
| `backend/app/models/profile_suppression.py` | 用户移除条目的墓碑，防止重建后复活 |
| `backend/app/models/profile_update.py` | 长期画像修正提案与确认状态 |
| `backend/app/models/job_analysis.py` | JD 分析结果与要求条目 |
| `backend/app/models/career_report.py` | 版本化报告，`(user_id, version)` 唯一约束 |
| `backend/app/models/conversation.py` | 多轮对话消息持久化 |
| `backend/app/models/run.py` | `AgentRun` / `RunStep` / `RunEvent` / `RunScope`：后台运行、代次、租约、fencing、事件序号 |
| `backend/app/models/wiki.py` | `WikiPage` / `WikiRevision`：页面、版本、引用、链接关系 |
| `backend/app/models/access_token.py` / `audit.py` / `evaluation.py` / `account_deletion.py` | 令牌、不含原文的审计、评测记录、账号删除回执 |
| `backend/app/models/learning.py` | 画像推荐 `SavedJob` / `LearningProgress`：用户保存的 JD 与学习计划进度 |
| `backend/app/models/assessment.py` | 画像推荐 `AssessmentResult` / `UserConstraint`：自陈测评与约束，独立于事实画像 |
| `backend/app/models/profile_extension.py` | 画像推荐 `DimensionDefinition` / `ProfileExtension`：用户可选画像维度 |
| `backend/app/schemas/*.py` | Pydantic 请求/响应契约：auth、chat、evidence、job、profile、report、run、wiki、evaluation、privacy；画像推荐新增 catalog、profile_overview、assessment（快测/量表/约束/维度/画像模式/故事） |
| `backend/migrations/versions/*.py` | Alembic 迁移：初始表、会话、SourceDocument/ParsedBlock、content_hash、report version 唯一、suppression、Wiki、Run、血缘保留；画像推荐 head `d0e1f2a3b4c5` 建 saved_jobs/learning_progress/assessment_results/user_constraints/dimension_definitions/profile_extensions |

### 4.4 业务服务（`backend/app/services/`）

| 文件 | 放的是什么代码 |
| --- | --- |
| `evidence.py` | 证据写入、去重、来源追加、删除联动 |
| `backend/app/ingestion/claim_strength.py` | 粘贴文本的分句标注和历史纯收藏判断，导入、确定性画像、模型引用过滤共同使用 |
| `source_ingestion.py` | 标准化导入流程，把 SourceDocument/ParsedBlock 转成 Evidence |
| `profile.py` / `profile_updates.py` | 画像重建、条目抽取、修正提案的原子确认 |
| `jobs.py` / `job_requirements.py` / `learning_path.py` | JD 逐条匹配、权重评分、按每周小时排学习路线 |
| `reports.py` | 八章节报告生成、版本分配、过期标记 |
| `knowledge.py` | 知识模式切换的公共逻辑 |
| `wiki_pages.py` | Wiki 页面唯一写入口：版本、乐观并发、表格行守卫、回滚 |
| `citations.py` | 回答/页面的引用允许集与 ID 规整 |
| `privacy.py` | 导出、删除、账号清理、向量补偿 |
| `audit.py` / `connectors.py` / `evaluation.py` | 审计记录、连接器服务、评测服务封装 |
| `profile_overview.py` | 画像推荐只读画像聚合与 agent-manifest；覆盖度按有效 Evidence 计算，不用 `ProfileItem.id` 做锚点 |
| `profile_view_preferences.py` | 画像推荐补充轮：五种画像模式与模块开关的常量；只改展示/软排序，不碰事实与匹配分 |
| `recommendation.py` | 画像推荐确定性方向/课程推荐与 learning_path v2；不联网、不接人格测评 |
| `assessment.py` | 画像推荐自陈结果的唯一落库路径：`mark_reports_stale` 标记依赖报告、`record_assessment` 原子写入并提交、`delete_assessment_result` 删除后同步标 stale；旧快测与量表共用，避免两套逻辑漂移 |
| `backend/app/catalog/loader.py` + `roles.json` / `courses.json` | 画像推荐本地教学目录与校验（重复 ID、悬空先修、URL 白名单、日期）；坏数据直接报错 |

### 4.5 Agent、模型、检索、Wiki

| 文件 | 放的是什么代码 |
| --- | --- |
| `backend/app/graph/career.py` | LangGraph 状态图：意图判断、检索、回答、画像修正、结束条件；短对话同步路径 |
| `backend/app/graph/checkpoint.py` | 按线程清理旧版 PostgreSQL checkpoint。当前聊天图按请求运行，SQL 消息表提供历史 |
| `backend/app/llm/provider.py` | 模型 Provider 抽象与 Demo/DeepSeek/OpenAI-compatible/Qwen 路由；`MODEL_ROLE_BINDINGS` 按 answer/wiki/analysis/profile 分角色，`get_llm(role=...)` 是角色入口 |
| `backend/app/retrieval/providers.py` | Dense/Sparse Provider 抽象、Qdrant/本地降级、`MODEL_ROLE_BINDINGS` 之外的检索配置入口；两阶段重排由 `retrieval/reranker.py` 的 `build_reranker` 实现（coarse top-15 → fine top-5，失败降级到词法分） |
| `backend/app/retrieval/qdrant_store.py` | Qdrant 集合、upsert/delete、用户隔离、payload 过滤 |
| `backend/app/retrieval/hybrid.py` | 混合检索与 RRF 融合；`hybrid_search()` 和 `dense_only()` 已修复 content/evidence_id 错配 |
| `backend/app/retrieval/reranker.py` | 两阶段重排：`build_reranker()`、coarse top-15 → fine top-5、阶段失败降级词法分 |
| `backend/app/retrieval/service.py` | 检索服务门面：`RetrievalService.search()` / `get_evidence_by_id()` / `search_wiki()`，给 graph、API 与评测统一接口 |
| `backend/app/wiki/compiler.py` | 从证据编译 Wiki 主题页，带引用；调用短句柄表与守卫 |
| `backend/app/wiki/handles.py` | `c000` 短句柄注册/解析、未知句柄丢弃、页内标记清理 |
| `backend/app/wiki/tables.py` | 表格行身份守卫：重写若丢失源表行会被拒绝 |
| `backend/app/wiki/search.py` | Wiki 命中转换为可引用的检索结果 |
| `backend/app/profile/extractor.py` / `llm_extractor.py` / `alias_match.py` / `catalog.py` | 画像抽取、模型抽取、别名匹配、字段目录 |

### 4.6 导入、连接器、运行时、MCP

| 文件 | 放的是什么代码 |
| --- | --- |
| `backend/app/ingestion/contract.py` | `ParsedDocument` / `ParsedBlock` 解析契约 |
| `backend/app/ingestion/files.py` | PDF/DOCX/XLSX/TXT/MD/CSV 解析；扫描页标记待 OCR，不伪造文本 |
| `backend/app/ingestion/media.py` | 图片/音视频处理，OCR/ASR 可选接入 |
| `backend/app/ingestion/chunking.py` | 分块策略 |
| `backend/app/ingestion/html_export.py` | 画像推荐补充轮：用户另存 HTML 与导出 ZIP 的本地解析；标准库 HTMLParser，跳过 script/style，ZIP 拒绝路径穿越/超大成员；不联网、无 bs4/lxml 依赖 |
| `backend/app/connectors/bilibili.py` / `weibo.py` / `browser_capture.py` / `base.py` | 平台导出解析与浏览器采集连接器；画像推荐补充轮：采集平台扩到掘金/CSDN/知乎/小红书/GitHub，新增 `authored`/`merged` kind（按 `self_reported_published`），互动仍是 `preference_signal` |
| `backend/app/connectors/registry.py` | 画像推荐补充轮：来源注册表，按 A 用户导出 / B 当前页采集 / T 自备只读令牌 / C 需授权标注；OAuth 标为 `available: false`，不假装可用 |
| `backend/app/connectors/github.py` | 画像推荐补充轮：GitHub 自备只读令牌导入；`httpx` 直连 `api.github.com`，只读仓库元数据与 README（截断 6000 字符），令牌不写库/日志/证据，`external_id` 带 `pushed_at` 以便新推送才产生新证据 |
| `backend/app/assessment/` | 画像推荐补充轮：本地量表模块。`data/*.json` 放三份题库（32/48/20 题）与许可、免责声明；`loader.py` 校验 ID/维度/双极平衡/反向题并输出去掉计分键的公开视图；`scoring.py` 确定性计分（80% 门槛、接近中点、RIASEC 代码与一致性、大五反向题与分档），不引入第三方量表库 |
| `backend/app/connectors/public_link.py` | 画像推荐补充轮：用户粘贴公开链接生成待确认证据卡；**从不请求 URL**，清掉 query token，按自报处理 |
| `backend/app/runtime/store.py` | Run 存储核心：`submit/get_run/claim/decide/cancel/end/dispatch/event/step`；提交幂等、pending 配额、三代 scope（input/deletion/target）、租约、fencing token、终态清 payload/upload。运行时补充轮：`event()` 与 `end()` 改为 async，事件序号用 `UPDATE ... RETURNING` 在数据库层原子自增，避免并行 progress 丢号 |
| `backend/app/runtime/worker.py` | Worker 主循环：claim、执行、心跳、恢复、失败重试 |
| `backend/app/runtime/operations.py` | 长任务操作分发：导入、Wiki 编译、岗位分析、报告 |
| `backend/app/runtime/agents.py` | 结构化 specialist 工作流，把复杂任务拆成可恢复步骤。运行时补充轮：`Coordinator` 预算参数化（默认仍为 2）、失败补发 `step.failed`、记录 `duration_ms`；新增只读 `profile_cartographer`/`role_scout`/`curriculum_planner`，`delegate_many()` 仅用于 `PARALLEL_SAFE_ROLES` 的无依赖并行 |
| `backend/app/runtime/parse_input.py` | Run payload / upload 输入解析 |
| `backend/app/runtime/index_outbox.py` | 持久索引待办，PostgreSQL 行锁领取，SQLite 使用写事务串行；本地检索模式也消费删除 |
| `backend/app/runtime/deletion_work.py` | 跨存储删除任务的租约、重试和清理回执 |
| `backend/app/runtime/reindex.py` | 维护窗口内全量重建并核对 Qdrant 目标集合 |
| `backend/app/retrieval/generations.py` / `backend/app/models/index_generation.py` | 保存已使用的向量集合，隐私清理按登记范围处理 |
| `backend/migrations/versions/e1f2a3b4c5d6_*` → `14c5d6e7f8a9_*` | 本轮的令牌、运行时、隐私清理、向量世代与历史审计升级 |
| `backend/app/mcp/server.py` | MCP 工具与资源；`create_server()` 支持 stdio 与 Streamable HTTP；工具 list_generate_career_report/generate_career_report/list_profile/list_reports/get_report/list_jobs/analyze_job/get_job_analysis（共享 services），另有 `search_evidence` / `upsert_profile` 两个 local-only 便利工具；资源 careerlens://profile/reports/jobs/evidence；和 API 共用 scope 审计，不另起业务实现 |
| `backend/app/security/auth.py` | token/scope 校验、用户隔离、`required` 模式守卫 |

### 4.7 观测、评测

| 文件 | 放的是什么代码 |
| --- | --- |
| `backend/app/observability/tracing.py` / `metrics.py` | OpenTelemetry 配置；`metrics.py` 是工作台展示用的内存模型调用统计 |
| `backend/app/observability/prometheus.py` | `GET /metrics` 的计数器与延迟直方图；纯 ASGI 中间件（`BaseHTTPMiddleware` 会缓冲 SSE 流）。标签用路径模板，未知路径归为 `unmatched` |
| `backend/app/evaluation/runner.py` | 评测执行、微平均 F1 等指标 |
| `backend/app/evaluation/regression.py` | 回归门禁 |
| `backend/app/evaluation/cli.py` | 评测命令行 |
| `backend/app/evaluation/dev_benchmark*.json` / `sample_*.json` | 开发集与基线快照，不代表真实准确率 |
| `backend/tests/` | 30+ 个测试文件；按主题命名，`test_run_runtime.py`、`test_wiki_compile.py`、`test_knowledge_mode.py`、`test_source_dedup.py` 是核心回归；画像推荐新增 `test_import_result_contract.py`、`test_profile_overview.py`、`test_catalog.py`、`test_recommendation.py`、`test_learning_progress.py`、`test_assessment.py`、`test_runtime_specialists.py`；补充轮新增 `test_assessment_instruments.py`（许可字段、计分、API）与 `test_github_connector.py`（MockTransport，无真实网络） |

### 4.8 后端数据流

```text
HTTP/MCP 请求
  → api/routes/*（鉴权与 schema 校验）
  → services/*（业务事务）
  → models/* + core/database（PostgreSQL）
  → retrieval/*（Qdrant / 本地降级）+ llm/*（Demo/真实模型）
  → graph/career.py（Copilot 多轮）
长任务：
  api/routes/runs.py → runtime/store.py（Run/Step/Event/代次）
  → runtime/worker.py claim → operations.py → services/*
  → index_outbox.py 补偿 Qdrant
  → SSE/轮询把 RunEvent 推给前端 run-center.tsx
```

---

## 5. frontend/：界面源码地图

> 写前端代码前还要遵守 `frontend/AGENTS.md`（Next.js 自动生成规则）。

| 路径 | 放的是什么代码 |
| --- | --- |
| `frontend/package.json` | Next.js 16 / React 19 / TypeScript 依赖与脚本 |
| `frontend/next.config.*` / `tsconfig.json` / `eslint.config.*` | 构建、类型与 lint 配置 |
| `frontend/app/layout.tsx` | 根布局、全局样式与站点壳 |
| `frontend/app/page.tsx` | 公开首页：左侧文案 + 右侧证据链卡片的两栏 Hero + 真实产品截图主视觉；暖白编辑风的入口 |
| `frontend/app/globals.css` | 只做 `@import` 入口，按层引入 `app/styles/` 下五个文件；不要再往这里加规则 |
| `frontend/app/styles/tokens.css` | **唯一**设计令牌层：暖纸 `--bg #f1ede1`、墨 `--ink #1b1912`、赤陶 `--brand #a3441d`、深青 `--pine #1d4f45`、字号阶、圆角（4–13px）、阴影、`--shell:1200px`。`--sans/--serif` 在 `base.css` 的 `body` 上重新声明，因为 next/font 把 `--font-*` 挂在 body，`:root` 里引用会解析成空值 |
| `frontend/app/styles/base.css` / `shell.css` / `landing.css` / `workspace.css` | 基础排版与控件、站点外壳、营销页、工作台；新增样式按归属放进对应层 |
| `frontend/app/start/page.tsx` | 新手开始页 |
| `frontend/app/demo/page.tsx` | 演示页 |
| `frontend/app/architecture/page.tsx` | 公开架构展示页 |
| `frontend/app/workspace/page.tsx` | 工作台渲染层（约 340 行）：工具头、五步流程条、各区块 JSX；不再持有业务状态 |
| `frontend/e2e/happy-path.spec.ts` | Playwright 端到端：导入证据 → 画像 → 岗位匹配（真实确认 + worker）→ 报告；另有首页跳转与 404。`PW_CHANNEL=msedge` 可复用本机浏览器 |
| `frontend/lib/use-workspace.ts` | 工作台全部状态与副作用（约 520 行）：32 个 state、26 个 handler、挂载时恢复已保存画像；改交互先看这里 |
| `frontend/app/error.tsx` / `loading.tsx` / `not-found.tsx` | 路由级错误、加载与 404 状态页；样式在 `styles/shell.css` 的 `state-*` 段 |
| `frontend/components/site-sidebar.tsx` | 全站左侧固定导航（概览 / 工作台分区 / 资源），按路径高亮；窄屏折叠为顶部条 |
| `frontend/components/site-chrome.tsx` | 共享顶部面包屑条与页脚 |
| `frontend/components/run-center.tsx` | 后台任务中心：进度、审批、取消、打开结果；消费 Run 事件；运行时补充轮 步名映射含 `profile_cartographer`/`role_scout`/`curriculum_planner` 与 `step.failed` |
| `frontend/components/import-result-card.tsx` | 导入结果卡 导入结果卡：可读/待 OCR/重复数、告警、证据定位与删除 |
| `frontend/components/profile-insights.tsx` | 画像概览 画像分布、技能矩阵、证据时间线、覆盖度，均带文字表格降级 |
| `frontend/components/score-breakdown.tsx` | 画像概览 分数构成与报告八章全览 |
| `frontend/components/learning-board.tsx` | 学习看板 职业方向卡、课程目录、按周学习看板与进度 |
| `frontend/components/assessment-card.tsx` | 测评区编排：加载量表清单与历史结果、切换量表、提交后回显、历史查看/删除；具体答题、结果渲染、约束与维度分别下沉到下面四个组件 |
| `frontend/components/assessment-quick-form.tsx` | 5 题工作方式快测（旧接口），自带题目加载与同意勾选 |
| `frontend/components/assessment-instrument-runner.tsx` | 单份量表分页答题：8 题/页、进度、80% 门槛、清空重答、许可说明；父级用 `key` 切换量表时重置 |
| `frontend/components/assessment-result-view.tsx` | 只读结果渲染：四维双极条、RIASEC 条形与方向线索、大五分档、方法/许可/免责声明 |
| `frontend/components/assessment-profile-tools.tsx` | 约束条件与自定义维度：只影响过滤与展示，不参与匹配分 |
| `frontend/components/profile-enhancements.tsx` | 画像推荐补充轮：画像模式选择、模块开关、能力证据卡、面试故事库 |
| `frontend/components/import-hub.tsx` | 画像推荐补充轮：来源注册表展示、公开链接证据卡表单、GitHub 自备令牌表单与最小权限创建教程 |
| `frontend/lib/assessment-format.ts` | 画像推荐补充轮：测评纯函数（分页、作答统计、80% 门槛、结果标题、分数裁剪、双极强侧、分档色调），Node 单测直接导入 |
| `frontend/lib/api.ts` | 后端 API 客户端、SSE 手动 `TextDecoder` 解码、请求封装；画像推荐新增 `EvidenceItem` 完整类型、`getProfileOverview`/`getAgentManifest`、目录/推荐/保存 JD/学习进度/测评/维度的类型与函数 |
| `frontend/lib/run-events.ts` | Run 事件解析与状态归并 |
| `frontend/lib/profile-views.ts` | 画像概览 纯函数：技能矩阵、能力卡、证据时间线、分数拆解、类别分布聚合 |
| `frontend/lib/browser-capture.ts` | 浏览器采集页通信 |
| `frontend/lib/demo-story.ts` | 工作台预填的虚构案例数据 |
| `frontend/lib/*.test.mjs` | 浏览器采集与 Run 事件的小范围回归 |
| `frontend/public/images/workspace-preview.jpg` | 首页真实产品截图主视觉（新版界面） |
| `frontend/AGENTS.md` | Next.js 生成的框架规则；不要删除，提交它可保持工作树干净 |

**视觉现状**：公开页与工作台都是暖白编辑风（象牙白底、墨黑字、黄铜强调色、克制动画），不再是深色改版。23 张产品截图已按新界面重拍，位于 `docs/assets/*.jpg`。

---

## 6. docs-site/：教程站地图

| 文件 | 放的是什么代码/资料 |
| --- | --- |
| `docs-site/index.html` | Docsify 壳：`homepage: 'tutorials/从这里开始.md'`、`basePath: '/careerlens/'`、`relativePath: true`、`loadSidebar: true`、`search: { paths: 'auto', placeholder: '搜索文档', depth: 3 }` |
| `docs-site/_sidebar.md` | 在线侧栏；中文文件名与 8 篇概念课、各章入口都在这里 |
| `docs-site/build.py` | 把 `docs/`、`tutorials/`、`README.md` 打包到输出目录（CI 用 `_site`），改写 Markdown 链接、复制 `docs/assets` 截图、校验路径和锚点；必须传 `<output_dir>`，CI 还传 commit SHA |
| `docs-site/test_build.py` | 3 项导航回归：首页链接、链接改写、坏链检测 |
| `docs-site/mermaid-docsify.js` | Mermaid 渲染插件 |
| `docs-site/vendor/` | 本地固定的 Docsify、搜索、copy-code、tabs、Mermaid、Prism、Vue 资源；不读源码，除非排查插件 |
| `docs-site/vendor/VERSIONS.md` | 固定资源版本说明 |
| `docs-site/foundations-lab.html` | 浏览器中做的阶段 0 证据练习页 |
| `docs-site/.nojekyll` | 阻止 Jekyll 处理下划线文件 |

**构建规则**：改教程文件名或链接后必须跑 `python docs-site/build.py` 和 `python docs-site/test_build.py`；0 坏链/坏锚点才算完成。

---

## 7. docs/：公开技术文档地图

| 文件 | 主题 |
| --- | --- |
| `docs/README.md` | 技术文档入口与阅读顺序；结尾声明「文档与代码不一致以代码为准」 |
| `docs/architecture.md` | 服务分层、请求链路、数据边界、设计取舍 |
| `docs/data-and-evidence.md` | Evidence、画像、JD、报告的生命周期与删除联动 |
| `docs/phase-1-2-validation.md` | 第一/二期 A–D 验收、工作台操作、迁移配置 |
| `docs/phase-3-runtime.md` | 第三期 Worker、Run/Step/Event、审批、取消、重放、索引补偿 |
| `docs/job-matching-and-planning.md` | 评分权重、算例、排期、历史分析失效 |
| `docs/profile-and-recommendations.md` | 画像推荐导入结果卡、证据类型统一、画像概览、Agent 清单、目录推荐、多 JD 对比、测评边界、多 Agent 并发边界 |
| `docs/agent-and-retrieval.md` | LangGraph、混合检索、模型切换与降级、与 WeKnora/WorkBuddy 的实现对照 |
| `docs/integrations-and-security.md` | 导入、MCP、用户隔离、权限、公网边界 |
| `docs/evaluation-and-operations.md` | 评测口径、本地验收、故障定位 |
| `docs/api-and-configuration.md` | 完整接口、非 Docker 启动、迁移、真实模型与生产配置 |
| `docs/showcase.md` | 页面截图展示 |
| `docs/adr/README.md` | V4 决策索引：进程拓扑、API 基线、JSONL 协议、M0 原型边界 |
| `docs/adr/0004-m0-scripted-runner-prototype.md` | 自研 Runner 原型的验证结论、测试 ID 与未做项 |
| `docs/assets/*.jpg` | 23 张新版截图：页面总览、工作台各分区（导入/画像/匹配/报告/Copilot/测评/质量/数据）与公开页 |

---

## 8. tutorials/：公开课程地图

### 8.1 入口与支撑文件

| 文件 | 用途 |
| --- | --- |
| `tutorials/README.md` | 第一章八篇概念 → 跑产品 → 最小实现与 Agent 源码 → 知识库 → 任务与接入 → 画像和学习实战 → 选做与结课 |
| `tutorials/setup/动手准备.md` | 终端、编辑器、统一 Python 环境与 8000 / 8030 / 8031 的账号、数据交接 |
| `tutorials/从这里开始.md` | Docsify 首页；3 分钟证据判断题 |
| `tutorials/术语表.md` | 术语口径 |
| `tutorials/常见问题.md` | FAQ |
| `tutorials/更新记录.md` | 教程版本与修订过程，查「以前怎么改到现在」 |
| `tutorials/试学走查指南.md` / `试学模拟记录.md` | 模拟读者路线与卡点；不是真人验收 |
| `tutorials/静态观察路线.md` | 不能装 Docker 时的替代路线 |
| `tutorials/结课模板.md` | 可复跑结课交付模板 |

### 8.2 第一章：八篇概念课（`00-foundations/`）

| 文件 | 主题 |
| --- | --- |
| `00-1-Agent是什么.md` | 从林澈材料出发理解证据驱动 Agent |
| `00-2-提示词与证据.md` | 提示词、证据边界、不可编造结论 |
| `00-3-RAG与检索.md` | RAG 基础与项目里的检索位置 |
| `00-4-数据模型大白话.md` | Evidence / Profile / JD / Report 的关系 |
| `00-5-LangGraph与工作流.md` | 状态图、节点、边、checkpoint |
| `00-6-LangChain与模型工具.md` | **LangChain 入门教程**：模型、prompt、tool、chain 与项目使用 LangGraph 的关系；不是「项目没用 LangChain」的防御性说明 |
| `00-7-混合RAG与排名融合.md` | Dense + Sparse、RRF、reranker |
| `00-8-Wiki知识组织.md` | Wiki 编译、短句柄、表格守卫、版本 |

### 8.3 主章节与子系列

| 路径 | 内容 |
| --- | --- |
| `01-第一次跑起来.md` | 零基础安装、Docker、首次工作台操作 |
| `02-数据模型.md` | 数据模型与去重实验 |
| `03-解析层.md` | 多格式解析与 ParsedBlock |
| `04-检索Agent.md` | 检索 Agent、模式切换、RRF 实验（样板课） |
| `05-Wiki知识组织.md` | Wiki 编译、引用、版本、回滚 |
| `06-后台运行时.md` | Run/Step/Event、Worker、SSE、取消与恢复 |
| `07-接入与验证.md` | 工作台操作、API、评测与验证 |
| `07-A-MCP服务与ACP对照.md` | MCP 服务与 ACP 架构对照 |
| `08-advanced/08-1-真实模型.md` | 真实模型与 OCR/ASR 边界 |
| `08-advanced/08-2-评测.md` | 评测实验与指标 |
| `08-advanced/08-3-贡献与结课.md` | 贡献流程与结课交付 |
| `09-画像与自陈测评.md` | 自陈与事实对照、三份量表、约束与自定义维度、可选 GitHub 导入 |
| `10-导入与可回查画像.md` | HTML 导入和回查、收藏对照、覆盖度、显示偏好和面试故事 |
| `11-岗位对比与学习计划.md` | 延续第 10 篇账号，对比两份岗位、查找课程并保存进度 |
| `01-agent-design/` | 10 篇 Agent 源码课 + README + `lab/`；从请求状态、路由、工具、MCP、引用、会话到子 Agent 与综合跟做 |
| `01-agent-design/入门练习-从零写证据助手.md` | 从空目录写证据、检索和引用的最小实现，选做 FastAPI |
| `04-knowledge-base/` | 6 篇数据知识库课 + README + `lab/kb_practice.py`；去重、检索、Wiki 编译、表格保护、版本回滚、综合验收 |
| `setup/Python准备.md` | 选做 Python 环境准备 |

---

## 9. examples / eval / scripts / browser-helper / .github

| 路径 | 放的是什么 |
| --- | --- |
| `examples/tutorials/README.md` | 六个跟做脚本的依赖与命令索引 |
| `examples/tutorials/fixtures/hy4-lin-api.html` | 第 10、11 篇共用的合成 HTML 作业证据 |
| `examples/tutorials/read_mcp_report.py` | 用只读令牌从工具和资源两处读取第 07 篇的同一份报告 |
| `examples/tutorials/fixtures/{my_scale,work-style-neutral}.json` | 第 09 篇的量表包与可提交答案，原始数据在 assessment 目录 |
| `examples/tutorials/_client.py` | 教学脚本共用的轻量 API 客户端 |
| `examples/tutorials/lesson-01-evidence/` | 证据闭环练习 |
| `lesson-02-dedup/` | 去重预测练习 |
| `lesson-03-chat-modes/` | `rag/wiki/hybrid` 模式练习 |
| `lesson-04-events/` | 后台 Run/Event 练习 |
| `lesson-05-rrf/` | 离线 RRF 与自定义榜单练习 |
| `lesson-06-eval/` | 评测练习 |
| `examples/tutorials/fixtures/` | DOCX 合成夹具与生成脚本；共同正文复用同一证据 ID、两条来源 |
| `examples/bilibili-export.example.json` / `weibo-export.example.json` | 连接器示例导出 |
| `eval/README.md` / `eval/datasets/` / `eval/baselines/` | 评测说明、数据集、基线快照 |
| `scripts/docker-smoke.ps1` | 一次性合成资料全栈冒烟；覆盖导入→画像→岗位→报告→对话、双 Worker、SSE、Wiki、清理 |
| `browser-helper/` | 浏览器采集扩展：manifest、popup、采集与截图脚本、测试 |
| `.github/workflows/quality.yml` | PR/main 的后端、前端、Docker 冒烟质量门禁 |
| `.github/workflows/docs-pages.yml` | Docsify 打包与 GitHub Pages 部署 |
| `.github/workflows/release.yml` | Release 发布 |
| `.github/dependabot.yml` / `ISSUE_TEMPLATE/` / `pull_request_template.md` | 依赖更新与社区模板 |

---

## 10. 以前 → 现在：AI 必须知道的演进

### 10.1 产品代码版本线（以 `CHANGELOG.md` 为准）

| 版本 | 以前新增/变化 | 现在应当怎么理解 |
| --- | --- | --- |
| v0.1.0 | 证据导入、画像、JD、报告、LangGraph 对话、PostgreSQL、Qdrant、Provider 抽象、MCP、评测 | 基础闭环仍在，但很多实现已被后续版本加固；不要只看最初设计描述 |
| v0.2.0 | `ParsedDocument/ParsedBlock`、SourceDocument、源级去重、多轮消息、报告版本唯一、删除墓碑；恢复被 `.gitignore` 误排除的 `models/` ORM 包；修复 `hybrid_search` 错配 evidence_id、画像批准孤儿证据 | 解析与去重以当前 `ingestion/` + `models/parsed_block.py` 为准；早期「直接文本切块」说法已过时；新克隆导入 `app.models` 失败是历史问题 |
| v0.3.0 | Wiki 编译/版本/短句柄/表格行守卫、查询期 `rag/wiki/hybrid`、模型角色绑定、两阶段 reranker；修复 Wiki 引用导致 fallback KeyError | 知识组织以 `wiki/` + `services/wiki_pages.py` 为准；模式切换是**建索引/页面时决定、查询时切换**，不是每次重建 |
| v0.4.0 | 持久后台 Run、Worker/Coordinator、SSE、审批取消、租约恢复、fencing、索引 outbox、任务中心 | 长任务以 `runtime/` + `api/routes/runs.py` + `components/run-center.tsx` 为准；不要把长任务当成请求线程里的同步调用 |
| 未发布整改 | 分离 API/MCP/实例运维身份，靠持久任务清理外部副本，聊天上下文改用关系表，向量集合检查指纹 | 升级先运行迁移，维护窗口内重建旧向量集合；生产配置和恢复命令以 `docs/api-and-configuration.md` 为准 |

### 10.2 教程与站点（2026-11-24 → 2026-11-25）

| 事项 | 以前 | 现在 |
| --- | --- | --- |
| 阶段 0 | 4 篇零安装课，概念与源码之间有断层（T-16） | 8 篇概念课（00-1～00-8），每篇按 00-6 深度重写；00-6 是 LangChain 入门，不再写「项目没用 LangChain」 |
| 第三章 | 8–14KB，源码导读偏浅 | 10 课 + README，15–22KB/课，附 AST 练习闭环 |
| 第四章 | 8–11KB | 6 课 + README，17–22KB/课，按真实源码讲解析、去重、检索、Wiki |
| 第五至八章 | 部分 3.5–11KB | 按同深度加厚到 8.6–16KB；07 已够厚未改 |
| 首页视觉 | 深色改版被否定 | 暖白编辑风：象牙白、墨黑、黄铜、真实产品截图主视觉 |
| 截图 | 旧界面截图 | 23 张 `docs/assets/*.jpg` 按新界面重拍（1425×891），首页另有 `workspace-preview.jpg` |
| 文件名/链接 | 英文/混合命名、旧双目录地址、锚点未实校 | 中文文件名为主；兼容旧地址；build 校验 0 坏链/坏锚点 |
| 推送方式 | git HTTPS 502 / schannel 失败；本地 `git hash-object` 受 CRLF 影响产生假阴性 | 通过 Git Data API（blob→tree→commit→ref）推送，校验用原始字节算 SHA；本地 git 指针可能滞后，远端权威 |

### 10.3 本地管理文档

| 事项 | 以前 | 现在 |
| --- | --- | --- |
| 文档状态 | 早期草案、被裁剪设计、验收快照、当前计划混在根目录 | 当前有效文档在根目录，草案移入 `../历史归档/`，`../CareerLens文档导航.md` 是唯一状态真相源 |
| 教程方案 | 方案文档同时承担设计与执行状态 | `CareerLens零基础教程体系方案.md` 只讲设计原理；执行状态在台账 01/02/03/04 |
| 验收报告 | 过程记录很长 | 压缩为「留数据删过程」，作为当时快照保留，不改写历史数字 |
| AI 查阅 | 每次重新读目录、代码和管理文档 | 入口是 `AGENTS.md` → 本文件；工作区入口是 `../AI查阅导航.md` → `../CareerLens文档导航.md` |

---

## 11. 任务 → 先读什么

| 你要改/查什么 | 先读 | 然后读 |
| --- | --- | --- |
| 新增/修改 API | `api/router.py` → 对应 `api/routes/*.py` → `schemas/*.py` → `services/*.py` | `tests/` 对应测试、`docs/api-and-configuration.md` |
| 证据导入与去重 | `services/source_ingestion.py` → `services/evidence.py` → `models/evidence.py` → `ingestion/files.py` | `tests/test_source_dedup.py`、`tests/test_multiformat_parsing.py` |
| 画像与长期记忆 | `services/profile.py` → `profile_updates.py` → `graph/career.py` → `models/profile*.py` | `tests/test_atomic_profile_update.py`、`test_profile_correction_heuristics.py` |
| JD 匹配与排期 | `services/jobs.py` → `job_requirements.py` → `learning_path.py` → `models/job_analysis.py` | `docs/job-matching-and-planning.md`、`tests/test_job_intelligence.py` |
| Copilot / LangGraph | `graph/career.py` → `graph/checkpoint.py` → `services/citations.py` → `llm/provider.py` | `tests/test_profile_jobs_chat.py`、`docs/agent-and-retrieval.md` |
| 混合检索 / RRF / reranker | `retrieval/hybrid.py` → `retrieval/providers.py` → `retrieval/qdrant_store.py` → `retrieval/service.py` | `tests/test_qdrant_retrieval.py`、`examples/tutorials/lesson-05-rrf/` |
| Wiki 编译与版本 | `wiki/compiler.py` → `wiki/handles.py` → `wiki/tables.py` → `services/wiki_pages.py` | `tests/test_wiki_compile.py`、`tests/test_wiki_schema.py`、`05-Wiki知识组织.md` |
| 后台 Run / Worker / SSE | `runtime/store.py` → `runtime/worker.py` → `runtime/operations.py` → `api/routes/runs.py` | `models/run.py`、`components/run-center.tsx`、`tests/test_run_runtime.py` |
| MCP 工具 | `mcp/server.py` → `services/*` → `security/auth.py` | `tests/test_mcp.py`、`07-A-MCP服务与ACP对照.md` |
| 隐私与删除 | `services/privacy.py` → `models/account_deletion.py` → `runtime/index_outbox.py` | `tests/test_auth_privacy.py`、`docs/integrations-and-security.md` |
| 测评题库与计分 | `backend/app/assessment/data/*.json` → `assessment/loader.py` → `assessment/scoring.py` → `api/routes/assessment.py` → `services/assessment.py` | `docs/assessments.md`、`tests/test_assessment_instruments.py`、`frontend/components/assessment-*.tsx` |
| GitHub 令牌导入 | `connectors/github.py` → `api/routes/connectors.py` → `connectors/registry.py` → `components/import-hub.tsx` | `docs/github-token-import.md`、`tests/test_github_connector.py` |
| 评测 | `evaluation/runner.py` → `evaluation/regression.py` → `eval/` | `docs/evaluation-and-operations.md`、`lesson-06-eval/` |
| 前端页面/样式 | `frontend/app/page.tsx` 或 `workspace/page.tsx` → `globals.css` → `components/` → `lib/api.ts` | `frontend/AGENTS.md`、Next 本地 docs |
| 教程站发布 | `docs-site/index.html` → `_sidebar.md` → `build.py` → `test_build.py` | `.github/workflows/docs-pages.yml` |
| 改教程正文 | `tutorials/README.md` → 对应篇章 → `tutorials/更新记录.md` → `docs-site/build.py` | `../CareerLens教学项目台账/06-教程写作与验收规范.md` |
| 找配合教程的思考题 | `../CareerLens教程思考题集.md`（62 题：47 技术题 + 15 道写进简历的表达题） | 对应篇章正文与源码 |
| 判断当前状态 | 本文件 §0 → `CHANGELOG.md` → `../CareerLens文档导航.md` | 台账 01/02/03、验收报告（仅历史数据） |

---

## 12. 不要先读 / 容易误判的地方

1. **不要从 `app.asar.extracted/` 或 `weknora-source/` 推断 CareerLens 实现**；它们是外部参考。
2. **不要把验收报告里的数字当当前值**；它们各自标注了当时版本。当前值看本文件 §0。
3. **不要把「Demo 默认可跑」理解成「真实模型已验收」**；真实模型/OCR/ASR 仍是 Issue #3 和 M-02。
4. **不要把「旧库迁移未验」写成「代码不支持迁移」**；迁移存在，但独立环境旧库验收待 Issue #2。
5. **不要把「加厚完成」写成「真人已学会」**；T-07/T-18 仍待独立试学。
6. **不要因为本地 `git status` ahead 就重推**；远端内容与 Actions 是权威，本地引用可能滞后。
7. **不要在教程里恢复「LangChain 项目没用」的说法**；00-6 已是 LangChain 入门，项目用 LangGraph 编排、LangChain 作为基础概念讲解。
8. **不要直接改 `docs-site/vendor/` 里的压缩资源**；除非先读 `VERSIONS.md` 并在 CI 验证。

---

## 13. 维护约定

- 新增/删除/重命名源码文件、教程篇章、文档或工作流时，更新本文件对应表格。
- 发生版本发布或行为变化时，更新 `CHANGELOG.md`，并在本文件 §10 写清「以前 → 现在」。
- 本地状态变化更新 `../CareerLens文档导航.md` 与台账；不要改历史归档和旧验收报告。
- 发现文档与代码不一致，先按 §1.1 定真相，再修导航，不把猜测写进文档。

---

## 14. 本导航的审计边界

- 本文件基于 2026-11-25 的本地工作树与远端公开交付记录整理；已排除 `.venv/`、`node_modules/`、`__pycache__/` 等缓存目录。
- 它描述的是**代码与文档在哪里、职责是什么**，不是运行时质量证明：真实模型、OCR/ASR、旧库迁移、真人试学的结论仍以台账 03 / Issue #2 / #3 为准。
- 若源码与本文件冲突，以源码为准并立即修正本文件；若状态与远端 Actions 冲突，以远端为准。
