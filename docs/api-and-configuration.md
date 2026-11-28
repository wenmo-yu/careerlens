# API 与配置参考

> 本文按任务给出接口速查与配置示例；完整参数、请求体和响应模型以 Swagger 为准。README 保留精炼入口，日常使用优先看[交互工作台](../frontend/app/workspace/page.tsx)与[快速开始](../README.md#快速开始)。

## 服务地址速查

- Web 工作台：`http://localhost:3000/workspace`
- API 文档（Swagger）：`http://localhost:8000/docs`
- MCP Streamable HTTP：`http://localhost:8001/mcp`
- Qdrant Dashboard：`http://localhost:16333/dashboard`（`QDRANT_HTTP_PORT` 可改宿主机端口，容器内仍为 6333）

## 本地启动

需要 Python 3.11+；CI 固定 Node.js 22，本地建议使用同一版本。不要执行裸 `docker compose up -d`：基础 Compose 会同时启动 `migrate / api / worker / mcp / web / postgres / qdrant`，再在本机启 API 或前端会撞 8000、3000 端口，并可能造成两个 Worker 重复消费。按下面两条路径二选一。

### 路径 A：轻量模式（零容器，SQLite + local 检索）

与 CI 的端到端环境一致，无需 Docker、PostgreSQL 或 Qdrant：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".\backend[dev]"

$env:DATABASE_URL       = "sqlite+aiosqlite:///./careerlens.db"
$env:RETRIEVAL_BACKEND  = "local"
$env:CHECKPOINT_BACKEND = "memory"
$env:AI_PROVIDER        = "demo"
$env:AUTO_CREATE_SCHEMA = "true"

uvicorn app.main:app --app-dir backend --reload
# 另开终端，设置同样的环境变量后启动后台 Worker：
python -m app.runtime.worker
# 前端另开终端：
cd frontend
pnpm install
pnpm dev
```

用 `GET /health/live` 核对 API 是否启动。轻量模式的 `GET /health/ready` 只查数据库，SQLite 正常时返回 200。

### 路径 B：容器只提供依赖，本机跑 API / Worker / Web

```powershell
docker compose up -d postgres qdrant   # 必须显式限定服务

$env:DATABASE_URL       = "postgresql+asyncpg://career:career@localhost:5432/career"
$env:QDRANT_URL         = "http://localhost:16333"   # 注意不是 .env.example 的 6333
$env:RETRIEVAL_BACKEND  = "auto"                     # Qdrant 不可用时降级 local
$env:CHECKPOINT_BACKEND = "auto"
$env:AUTO_CREATE_SCHEMA = "false"

cd backend
python -m app.migration_runner
cd ..
uvicorn app.main:app --app-dir backend --reload
# 另开终端，设置同样的环境变量后：
python -m app.runtime.worker
# 前端另开终端：cd frontend; pnpm install; pnpm dev
```

完整容器方式仍用 `docker compose up -d --build`，由 `migrate` 服务先迁移，再启动 API、Worker、MCP 与 Web。

`migration_runner` 把新库和已有 Alembic 版本的库升级到 `head`。识别出旧版 `create_all()` 的完整表结构时，先补旧表并采用已知历史版本，再运行后续迁移。无法识别的无版本库会报错。生产使用 `AUTO_CREATE_SCHEMA=false`，升级前备份并停止旧版本的 API、Worker 和 MCP 写入。

---

打开 `http://localhost:8000/docs` 可看全部方法与模型。下面按任务列常用入口；代码声明的方法/路径组合远多于此，完整参数以 Swagger 为准。

**健康与观测**
- `GET /health/live`：进程存活检查，不探测依赖。
- `GET /health/ready` 先检查数据库。`local` 跳过向量服务，`auto` 在向量服务不可用或索引不兼容时返回 `200 degraded`，`qdrant` 模式返回 503。数据库不可用时均返回 503。
- `GET /metrics`：Prometheus 文本格式，可用 `METRICS_ENABLED=false` 关闭。

**导入与来源**
- `POST /api/v1/evidence/text|file|media`：文本、文件、图片 OCR / 音视频 ASR 同步导入。
- `POST /api/v1/runs/uploads`：文档/媒体走后台上传，返回 Run ID。
- `GET /api/v1/connectors/registry`：查看全部可用来源及可信等级。
- `POST /api/v1/connectors/browser/import`：导入当前页采集 JSON（扩展现支持八个平台）；互动只作兴趣线索。
- `POST /api/v1/connectors/public-link/import`、`POST /api/v1/connectors/github/import`：手填公开链接证据卡、自备只读令牌导入仓库元数据与 README。
- `POST /api/v1/connectors/bilibili/import`、`POST /api/v1/connectors/weibo/import`：用户导出的平台 JSON / CSV。
- `GET /api/v1/evidence`、`GET /api/v1/evidence/{id}`、`DELETE /api/v1/evidence/{id}`：列出、查看、删除证据。
- `GET /api/v1/evidence/search`、`POST /api/v1/evidence/reindex/{user_id}`：检索诊断与重建索引。

**画像与偏好**
- `GET /api/v1/profiles/{user_id}`、`POST /api/v1/profiles/{user_id}/rebuild`：读取与重建画像。
- `GET /api/v1/profiles/{user_id}/overview`、`GET /api/v1/profiles/{user_id}/agent-manifest`：画像统计与 Agent 能力清单。
- `POST /api/v1/profiles/{user_id}/proposals`、`POST /api/v1/profiles/proposals/{id}/decision`：草案 → 确认，不静默改长期画像。
- `GET/PUT /api/v1/profiles/{user_id}/dimensions`、`/view-preferences`、`/interview-stories`、`GET/PUT /api/v1/constraints/me`：自定义维度、展示模式、面试故事与约束。

**岗位、推荐与学习**
- `POST /api/v1/jobs/analyze`：同步岗位分析，返回 JobAnalysis ID。
- `GET /api/v1/catalog/roles`、`GET /api/v1/catalog/courses`：本地职业/课程目录。
- `POST /api/v1/recommendations/roles`、`POST /api/v1/recommendations/learning-plan`：确定性方向与课程推荐。
- `POST/GET /api/v1/saved-jobs`、`POST /api/v1/saved-jobs/compare`、`DELETE /api/v1/saved-jobs/{id}`：保存与对比最多 3 份 JD。
- `GET /api/v1/learning/plans/{plan_id}`、`POST /api/v1/learning/plans/{plan_id}/progress`：读取计划与写入看板进度。

**报告与对话**
- `POST /api/v1/reports`、`GET /api/v1/reports?user_id=...`、`GET /api/v1/reports/{id}/markdown`：生成、列出、下载版本化报告。
- `POST /api/v1/chat` 使用 LangGraph 编排本次对话。下一轮传入服务端返回的 `thread_id`，`messages` 最多返回最近 80 条消息。

**后台任务（Run / Worker）**
- `POST /api/v1/runs`、`POST /api/v1/runs/uploads`：提交 JSON 或文件上传任务。
- `GET /api/v1/runs`、`GET /api/v1/runs/{run_id}`、`/steps`、`/events`、`/stream`：列表、详情、步骤、事件与 SSE 续看。
- `POST /api/v1/runs/{run_id}/decision`、`POST /api/v1/runs/{run_id}/cancel`：确认与取消。

**持久 Agent（V4 M3–M8，默认关闭）**
- `POST /api/v1/agent/sessions`、`GET /agent/sessions`、`GET /agent/sessions/{id}/messages`：会话与历史。
- `POST /api/v1/agent/sessions/{id}/runs`：提交一轮，202 后由 scheduler 领取；`Idempotency-Key` 必须稳定。
- `GET /api/v1/agent/approvals`、`POST /agent/approvals/{run_id}/decision`：写工具审批；批准只表示允许一次幂等执行。
- `GET /api/v1/agent/artifacts`、`GET /agent/artifacts/{id}`：读取 `save_career_note` 产物。
- `POST /api/v1/agent/teams`、`GET /agent/teams/{team_id}/tasks`、`POST /agent/tasks/{id}/cancel`：M6 子任务、结果投影与父取消级联。
- `POST/GET /api/v1/agent/schedules`、`POST /agent/schedules/{id}/state`、`POST /agent/schedules/{id}/trigger`：M8 持久计划；`(schedule_id,due_at)` 幂等。
- `GET /api/v1/runtime/status`、`GET /api/v1/runtime/capabilities`：池/Run/审批/租约诊断与工具能力。
- 启动 scheduler：`AGENT_RUNTIME_ENABLED=true python -m app.runtime.agent.scheduler`。未启动时 Run 会停在 `queued`，这不是成功。
- 真实模型需 `AGENT_MODEL_PROVIDER=openai_compatible|deepseek|local` 与 `AI_API_KEY`；Demo/scripted 离线可用。真实供应商计费与 usage 未对账。

**Wiki、测评与评测**
- `POST /api/v1/wiki/compile`、`GET /api/v1/wiki`、`GET /api/v1/wiki/{slug}`、`/{slug}/revert`、`/{slug}/revisions`：编译、读取、回滚与版本。
- `GET /api/v1/assessments/instruments`、`GET /{id}`、`POST /{id}/submit`、`GET /api/v1/assessments/results`：自陈量表与结果。
- `POST /api/v1/evaluation/*`、`GET /api/v1/evaluation/runs`、`GET /api/v1/observability/summary|calls` 用于实例评测和观测，启用鉴权时使用独立 `OPS_ACCESS_TOKEN`。

**鉴权与隐私**
- `POST /api/v1/auth/register`、`POST /api/v1/auth/tokens`：Owner Token 与细粒度 Scope Token。
- `GET /api/v1/privacy/{user_id}/export|audit`、`DELETE /api/v1/privacy/{user_id}`：导出、审计、账号清理。
- `GET /api/v1/auth/me` 返回当前主体和会话权限。`GET /api/v1/privacy/deletions/{receipt_id}` 供运维查询后台清理进度。

**几个容易混的 ID**
- `Run ID`：由 `POST /api/v1/runs` 或 `/runs/uploads` 返回，用于所有 `/runs/{run_id}/*` 与 SSE。
- `JobAnalysis ID`：由 `POST /api/v1/jobs/analyze` 返回；传给报告/对话时字段名为 `job_analysis_id`。
- `report_id`：由 `POST /api/v1/reports` 返回，也可从后台 Run 的 `result.report_id` 取得。
- `plan_id`：**服务端不生成**，由调用方自选不透明字符串（如 UUID 或复用分析 ID），作为 `/learning/plans/{plan_id}` 的路径参数。

本地 `AUTH_MODE=disabled` 允许演示评测和观测。`optional` 和 `required` 使用 `Authorization: Bearer <OPS_ACCESS_TOKEN>`。`manage` 只管理令牌所属账号。

示例：

```powershell
$body = @{
  user_id = "demo-user"
  source_type = "self_statement"
  source_name = "career-goal"
  content = "我希望从事 AI Agent 与 LLM 应用开发，熟悉 Python 和 FastAPI。"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/evidence/text `
  -ContentType application/json `
  -Body $body
```

## 验证

```powershell
pytest backend/tests
ruff check backend
Set-Location frontend
pnpm lint
pnpm build
```

Docker 全栈启动后，可运行真实 PostgreSQL、Qdrant、API、MCP 与业务闭环验收；脚本默认在结束时删除测试账号及其全部数据：

```powershell
.\scripts\docker-smoke.ps1
```

如需保留生成的数据用于排查，追加 `-KeepData`。

## MCP

本地 stdio Server（适合由桌面客户端拉起进程）：

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./careerlens-demo.db"
$env:MCP_STDIO_USER_ID = "demo-user"
python -m app.mcp.server --transport stdio
```

Streamable HTTP Server（适合独立服务部署）：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://career:career@localhost:5432/career"
$env:MCP_AUTH_MODE = "required"
$env:MCP_AUTH_ISSUER_URL = "http://localhost:8000"
$env:MCP_RESOURCE_SERVER_URL = "http://localhost:8001/mcp"
$env:AUTH_TOKEN_PEPPER = "与 API 服务完全相同的随机密钥"
python -m app.mcp.server --transport streamable-http --host 0.0.0.0 --port 8001
```

先取得 API Owner Token，再用 `POST /api/v1/auth/tokens` 签发 MCP 凭证。读取场景使用 `{"user_id":"demo-user","name":"mcp-reader","scopes":["read"],"audience":"mcp"}`。签发时绑定 API 的 `MCP_RESOURCE_SERVER_URL`，它须与 MCP 服务对外资源地址相同。连接 `http://localhost:8001/mcp` 时发送该 MCP Bearer。工具用令牌的主体校验 `user_id`，导入、JD 分析和报告生成另外需要 `write`。

开发环境的 `stdio` 固定在 `MCP_STDIO_USER_ID`，适合独立演示库。可信本地客户端也可以通过进程环境注入 `MCP_STDIO_TOKEN`，主体与权限由这枚 MCP 令牌决定。生产选择鉴权后的 `streamable-http`。

提供的工具：

- Evidence：`list_user_content`、`get_evidence`、`import_text_evidence`、`search_evidence`
- 画像：`get_user_profile`
- 岗位：`list_job_analyses`、`analyze_job_description`
- 报告：`generate_career_report`、`list_career_reports`、`get_career_report`

资源包括 `profile://{user_id}`、`evidence://{user_id}/{evidence_id}`、`report://{user_id}/{report_id}`；另提供画像证据核验、岗位匹配复核、面试表达三个 Prompt 模板。

## 检索模式

默认配置是：

```text
RETRIEVAL_BACKEND=auto
RETRIEVAL_PROVIDER=hash
```

服务会优先使用 Qdrant；Qdrant 不可用时自动降级到进程内混合检索。检索响应中的 `retrieval` 字段会明确返回实际 backend、fusion、reranker 和 fallback 状态。

启用真实 Qwen3 Embedding/Reranker：

```powershell
pip install -e ".\backend[ml]"
$env:RETRIEVAL_BACKEND = "qdrant"
$env:RETRIEVAL_PROVIDER = "qwen"
$env:EMBEDDING_DIMENSION = "384"
uvicorn app.main:app --app-dir backend --reload
```

Qwen3 Embedding 默认固定模型 revision 并输出 384 维。改变模型、revision、维度或 Qwen 查询前缀时，准备新的 `QDRANT_COLLECTION`。应用在查询和写入时检查索引指纹和实际向量配置。旧集合缺少指纹时需从 SQL 重建。

使用包含 Qwen 依赖和 Hugging Face 模型缓存卷的容器：

```powershell
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up --build
```

模型首次使用会下载 Embedding 与 Reranker 权重。单个用户的索引补写可以调用现有接口，目标集合须与当前模型匹配。

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/evidence/reindex/demo-user
```

全量换代安排一个停止写入的维护窗口。先停 API、MCP 和 Worker，把旧集合名称加到 `QDRANT_CLEANUP_COLLECTIONS`，并为目标进程指定全新的 `QDRANT_COLLECTION`、模型配置和同一个数据库。运行 `python -m app.runtime.reindex --writes-paused`。命令逐批核对 Evidence ID 和租户，再把目标标为可用。成功后让 API、MCP 和 Worker 同时采用新配置。要保留旧集合，就继续把它纳入删除范围；要切回旧模型，先确认旧集合已补齐期间的新增和删除。

## 对话模型：API 与本地双路线

检索模型（`RETRIEVAL_*`）和生成模型（`AI_*`）相互独立。默认 `AI_PROVIDER=demo`，无需密钥，直接执行确定性逻辑。

使用 DeepSeek API：

```powershell
$env:AI_PROVIDER = "deepseek"
$env:AI_BASE_URL = "https://api.deepseek.com"
$env:AI_API_KEY = "你的密钥"
$env:AI_MODEL = "deepseek-flash" # 按所用服务实际支持的模型 ID 调整
uvicorn app.main:app --app-dir backend --reload
```

Docker Compose 的 `processing-environment` 锚点把 `AI_*` 与 `MODEL_ROLE_BINDINGS` 同时传给 **API、Worker 和 MCP**。改完 `.env` 必须重建这三者；只重建 API 会让 Copilot 用新模型，而后台报告仍被旧 Worker 处理：

```powershell
Copy-Item .env.example .env
# 编辑 .env：设置 AI_PROVIDER、AI_BASE_URL、AI_API_KEY、AI_MODEL、MODEL_ROLE_BINDINGS
docker compose up -d --build --force-recreate api mcp worker web
.\scripts\docker-smoke.ps1
```

验收两条链路时不要混用观测来源：

1. **Copilot（API 进程，role=`answer`）**：`POST /api/v1/chat` 的响应 `model` 字段应显示新 provider/model；同进程的 `GET /api/v1/observability/calls` 可看到该调用。
2. **后台报告（Worker 进程，role=`analysis`）**：`POST /api/v1/runs` 提交 `operation="report"`，拿 Run ID 轮询到 `succeeded`，从 `result.report_id` 读取报告，再看报告里的 `model_diagnostics`。`MetricsStore` 是进程内存储，Worker 的调用**不会**出现在 API 的 `/observability/calls`；同时检查 `fallback` 标志，避免把降级误判成模型已生效。

使用本地 Qwen（先用 vLLM、Ollama 等在 `8010` 端口暴露 OpenAI-compatible `/chat/completions` 接口，避开项目 MCP 的 `8001` 端口）：

```powershell
$env:AI_PROVIDER = "local"
$env:AI_BASE_URL = "http://localhost:8010/v1"
$env:AI_API_KEY = ""
$env:AI_MODEL = "Qwen/Qwen3-8B"
uvicorn app.main:app --app-dir backend --reload
```

`openai_compatible` 也可连接其他兼容服务。`AI_FAILURE_POLICY=allow_fallback` 允许相应阶段使用确定性结果，并附降级诊断。`strict` 将模型故障返回为明确的 503 或后台任务错误。
若 API 在 Docker 容器内运行，而 Qwen 服务在宿主机，`AI_BASE_URL` 应改为 `http://host.docker.internal:8010/v1`；容器中的 `localhost` 指向容器自身。

## 完整职业报告

完成画像和 JD 分析后，可以生成一份独立版本的职业报告：

```powershell
$body = @{
  user_id = "demo-user"
  job_analysis_id = "替换为岗位分析 ID"
} | ConvertTo-Json

$report = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/reports `
  -ContentType application/json `
  -Body $body

Invoke-WebRequest `
  -Uri "http://localhost:8000/api/v1/reports/$($report.id)/markdown" `
  -OutFile ".\careerlens-report.md"
```

报告包含个人画像、核心能力、证据目录、就业方向、岗位匹配、能力缺口、学习路线和行动建议。每次生成创建一个新版本。画像更新造成的普通过期报告仍可查阅。删除所引用的 Evidence 后，受影响的报告正文会被清除，详情和 Markdown 下载返回 410。

聊天记录由数据库中的会话与消息表保存。当前 LangGraph 运行在单次请求内。`CHECKPOINT_BACKEND` 和 `CHECKPOINT_DATABASE_URL` 继续用于清理旧部署的 PostgreSQL 快照。

## 个人数据来源与多模态导入

以 `GET /api/v1/connectors/registry` 为统一入口；注册表按真实能力标注来源，不把“需要用户授权”写成已实现：

| 渠道 | 当前支持 | 边界 |
| --- | --- | --- |
| 文本与文件 | 自述粘贴，PDF / DOCX / XLSX / CSV / TSV / TXT / Markdown，用户另存 HTML 与导出 ZIP | 旧 `.doc` 需另存为 `.docx` 或带文字层 PDF；扫描 PDF 页标为待 OCR；XLSX 由标准库解析 |
| 媒体 | 图片 OCR、音视频 ASR | 可选依赖，模型与效果需单独验收 |
| 浏览器当前页采集 | Bilibili、微博、抖音、掘金、CSDN、知乎、小红书、GitHub 的已加载可见内容 | 用户自己登录并手动采集；互动只作兴趣线索 |
| 平台导出文件 | Bilibili JSON、微博 JSON/CSV | 用户主动提供，重复外部 ID 跳过 |
| 公开链接证据卡 | 用户手填 URL、标题和说明 | 后端不访问链接，不证明账号归属 |
| GitHub 仓库 | 自备 fine-grained 只读令牌 | 只读元数据与 README；令牌不落库、不读 issues/PR |

Bilibili Connector 只接收用户主动提供的 UTF-8 JSON，不读取 Cookie、不模拟登录，也不绕过平台权限。支持根数组，或 `items`、`videos`、`archives` 数组：

```json
{
  "videos": [
    {
      "bvid": "BV1EXAMPLE",
      "title": "Agent 项目复盘",
      "description": "项目简介",
      "transcript": "字幕或用户导出的转录文本",
      "tags": ["AI", "LangGraph"],
      "published_at": "2026-10-15",
      "url": "https://www.bilibili.com/video/BV1EXAMPLE"
    }
  ]
}
```

同一个用户重复导入相同 `bvid` / `aid` / `id` 时会自动跳过。所有内容都会标准化为 Evidence，并保留平台 ID、原链接和发布时间。

微博 Connector 支持 UTF-8 JSON 和 CSV。JSON 可使用根数组，或 `statuses`、`posts`、`weibo`、`items` 数组；CSV 支持 `微博正文` / `text`、`发布时间` / `created_at`、`话题` / `topics`、`微博链接` / `url` 等中英文列名。正文中的简单 HTML 会被清洗，话题和转发内容会进入 Evidence；缺少微博 ID 时使用发布时间与正文生成稳定内容指纹，因此重新排序后重复导入仍能正确跳过。示例见 [`examples/weibo-export.example.json`](../examples/weibo-export.example.json)。

可选的 [`browser-helper/`](../browser-helper/README.md) 是 Chrome/Edge 本地页面采集工具：用户在 Bilibili、微博、抖音、掘金、CSDN、知乎、小红书或 GitHub 自己的页面登录、滚动加载，多次点击扩展汇总当前已加载的发布或互动条目，移除误采项并导出 JSON。工作台可逐条勾选，只有确认后才会写入 Evidence。扩展不读取 Cookie，也不提供后台同步；单次读取最多 100 条、一个分组最多保留 200 条，后端单文件最多 200 条且 2 MB。它不保证完整账号历史；点赞、收藏、关注仅作为兴趣线索，不直接推断技能。页面结构变化时可能漏项，详见[使用说明与限制](../browser-helper/README.md)。

GitHub 走「用户自备只读令牌」，不需要注册 OAuth 应用：

```bash
curl -X POST http://localhost:8000/api/v1/connectors/github/import \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u1","token":"github_pat_xxx","repos":["owner/name"]}'
```

`repos` 为空时取最近推送的 10 个自有仓库；只读元数据与 README（单个仓库最多 6000 字符）；令牌只在本次请求内存中使用，不落库、不写日志。创建最小权限令牌的步骤见 [GitHub 仓库导入](github-token-import.md)。

启用 OCR / ASR：

```powershell
pip install -e ".\backend[multimodal]"
$env:WHISPER_MODEL = "small"
$env:WHISPER_DEVICE = "cpu"
$env:WHISPER_COMPUTE_TYPE = "int8"
uvicorn app.main:app --app-dir backend --reload
```

或使用容器：

```powershell
docker compose -f docker-compose.yml -f docker-compose.multimodal.yml up --build
```

图片支持 PNG、JPG、WEBP、BMP；音视频支持 MP3、WAV、M4A、MP4、MOV、WEBM、MKV。首次使用会下载 OCR / Whisper 模型，因此建议为模型缓存保留持久卷。

## 自陈测评

三份本地量表（`work_style_4d` 32 题、`riasec_interest` 48 题、`big_five_20` 20 题）都由项目自写并固定版本，接口会返回许可与免责声明：

```bash
# 清单
curl http://localhost:8000/api/v1/assessments/instruments

# 题目（不含计分键与反向标记）
curl http://localhost:8000/api/v1/assessments/instruments/work_style_4d

# 提交；至少回答 80%，且每个维度至少一半
curl -X POST http://localhost:8000/api/v1/assessments/instruments/work_style_4d/submit \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u1","consent":true,"answers":{"ws-ei-01":5,"ws-ei-05":4}}'
```

不足题量返回 422 并说明还差多少；未答项不插补。结果写入 `assessment_results`，`source=self_report`，不进入事实画像、不改岗位匹配分；画像概览的 `assessments` 只回显每个量表最近一次。计分公式、许可比对与结果边界见 [测评题库与许可](assessments.md)。

## 监控指标

`GET /metrics` 以 Prometheus 文本格式暴露：

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `careerlens_http_requests_total` | counter | 按 `method` / `path` / `status` 计数 |
| `careerlens_http_request_duration_seconds` | histogram | 端到端耗时，桶从 10ms 到 60s |
| `careerlens_http_requests_in_flight` | gauge | 当前并发请求数 |

`path` 使用路由模板（`/api/v1/profiles/{user_id}`），不是原始 URL，因此不会因为用户变多而爆掉序列数；未匹配路径合并为 `unmatched`。

该端点与 `/health/*` 一样不带鉴权、也不携带个人数据。直接暴露到公网时用 `METRICS_ENABLED=false` 关闭，或在网关层限制来源。

```bash
curl -s http://localhost:8000/metrics | head -20
```

## 评测与模型观测

评测不使用 LLM-as-a-Judge，而是与冻结标签中的画像、Evidence 和 JD 状态比较。网页和 CI 默认运行 v3 合成开发基准：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/evaluation/regression/benchmark
```

v3 包含 20 个场景、80 条 Evidence、40 个检索问题，测试中英文别名、strong / partial / gap、重复证据、否定表述、纯缺口和非技术干扰样本。本地规则链路在该集上达到四项开发指标 100%，包括 Evidence Recall@5；这不是独立人工标注的真实用户分布，也不是 Qdrant/Qwen 模型链路的准确率。自定义数据集格式见 [`eval/README.md`](../eval/README.md)。

真实 LLM 调用会记录 operation、provider、model、成功状态、延迟和 Token，不记录 Prompt、API Key 或个人 Evidence 原文。配置每百万 Token 单价后可计算成本：

```text
AI_INPUT_PRICE_PER_MILLION=0
AI_OUTPUT_PRICE_PER_MILLION=0
```

运行冻结回归门禁（任一指标退化时进程返回 `1`）：

```powershell
Set-Location backend
python -m app.evaluation.cli `
  --dataset app/evaluation/dev_benchmark_v3.json `
  --baseline ../eval/baselines/careerlens-dev-benchmark-v3.json
```

仓库中的 [Quality Gate](../.github/workflows/quality.yml) 配置后端 lint、测试与覆盖率/回归门禁，前端 lint、Node 单测与生产构建，Playwright 端到端，以及 Docker 全栈 Smoke Test；浏览器采集扩展另有捕获/合并检查。依赖审计在独立的 [Dependency Audit](../.github/workflows/security.yml) 中运行，Pages 构建部署在 [Docsify Pages](../.github/workflows/docs-pages.yml) 中运行。

启用 OpenTelemetry OTLP/HTTP 追踪：

```powershell
pip install -e ".\backend[observability]"
$env:OTEL_ENABLED = "true"
$env:OTEL_SERVICE_NAME = "careerlens-api"
$env:OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = "http://localhost:4318/v1/traces"
uvicorn app.main:app --app-dir backend --reload
```

需要向托管端点添加认证时，使用逗号分隔的 `OTEL_EXPORTER_OTLP_HEADERS=key=value,tenant=value`。Span 只包含路由信息、operation、provider、model、状态、Token 与估算成本；不会写入 Prompt、密钥或 Evidence 原文。

LangGraph 已带 LangSmith 集成，需要时仅设置：

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的密钥
LANGSMITH_PROJECT=careerlens-production
```

OTLP 适合统一接入 Collector/Jaeger/Grafana 等后端；LangSmith 是额外的 Agent 调试视图，两者均为可选能力，不影响本地 Qwen 或 DeepSeek/OpenAI-compatible 双路线。

## 鉴权与隐私控制

鉴权支持三种模式：

- `disabled`：默认本地演示模式，不要求 Token。
- `optional`：无 Token 时兼容旧客户端；提供 Token 时严格校验用户和 Scope。
- `required`：生产模式，所有个人数据接口必须携带 Bearer Token。

生产要求 `APP_ENV=production`、`AUTH_MODE=required`、高熵 pepper、明确 HTTPS 来源，以及适用的向量服务密钥。注册和 Prometheus scrape 默认关闭。启动并完成迁移后，从可信运维终端签发拥有者令牌。

```powershell
docker compose -f docker-compose.yml -f docker-compose.production.yml exec api python -m app.security.provision account-id
```

命令只打印一次明文。持有者将它填入工作台的访问令牌输入框。账户已有令牌且失效时，运维核对归属后可追加 `--recover`，它会撤销该账号的旧令牌。开发环境也可从 HTTP 注册。

```powershell
$headers = @{ "X-Registration-Secret" = $env:AUTH_REGISTRATION_SECRET }
$body = @{ user_id = "demo-user"; name = "owner" } | ConvertTo-Json
$created = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/auth/register `
  -Headers $headers -ContentType application/json -Body $body
$env:CAREERLENS_TOKEN = $created.token
```

后续请求使用：

```powershell
$headers = @{ Authorization = "Bearer $env:CAREERLENS_TOKEN" }
Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/privacy/demo-user/export `
  -Headers $headers
```

Scope 包括 `read`、`write`、`export`、`delete`、`manage`。数据库保存带 pepper 的哈希和受众。新令牌默认 24 小时，可用 `AUTH_TOKEN_LIFETIME_HOURS` 调整。升级时已有令牌只可访问 API，并从迁移时起保留七天。需要 MCP 的调用方重新签发 `audience=mcp` 的令牌。

轮换时各进程使用相同配置。把原 pepper 放入 `AUTH_TOKEN_PREVIOUS_PEPPER`，声明带时区的截止时间 `AUTH_TOKEN_PREVIOUS_UNTIL`，再把 `AUTH_TOKEN_KEY_VERSION` 递增一并配置新 pepper。窗口内重签 API 与 MCP 凭证，过期后移除旧值。确认密钥泄露时可直接停用旧 key 并走运维重签。

整账号删除要求 `delete` 或 `manage`。数据库提交后访问即关闭，原令牌失效，该账号标识随即停用。`cleanup_status` 显示外部向量及旧 checkpoint 清理状态。部署运维凭证可查询 `GET /api/v1/privacy/deletions/{receipt_id}`，并在修复外部依赖后用 `POST /api/v1/privacy/deletions/{receipt_id}/retry` 重试失败目标。

生产 Compose 需要支持 `!reset` 的 Compose 版本，例如 v2.36.2。它解除数据库及向量服务的宿主机端口映射，Web、API 和 MCP 监听宿主机回环地址，供 HTTPS 反向代理接入。

```powershell
Copy-Item .env.production.example .env
# 编辑 .env，将全部 replace-with-* 值替换为真实随机值和模型配置
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

`.env`、本地数据库、上传内容和模型缓存均已在 `.gitignore` 中排除。公开部署仍需在容器前配置 HTTPS 反向代理，并在网络层限制 PostgreSQL 与 Qdrant 端口。


