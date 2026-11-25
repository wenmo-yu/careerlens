# API 与配置参考

> 本文收纳完整的接口清单与配置示例，README 保留精炼入口。日常使用优先看[交互工作台](../frontend/app/workspace/page.tsx)与[快速开始](../README.md#快速开始)。

## 服务地址速查

- Web 工作台：`http://localhost:3000/workspace`
- API 文档（Swagger）：`http://localhost:8000/docs`
- MCP Streamable HTTP：`http://localhost:8001/mcp`
- Qdrant Dashboard：`http://localhost:16333/dashboard`（`QDRANT_HTTP_PORT` 可改宿主机端口，容器内仍为 6333）

## 非 Docker 本地启动

需要 Python 3.11+ 与 Node.js 20.9+。Compose 会先跑一次 `migrate` 服务，再启动 API 与 MCP；手动启动时顺序由你负责：

```powershell
Copy-Item .env.example .env
docker compose up -d          # 只起 PostgreSQL 与 Qdrant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".\backend[dev]"
uvicorn app.main:app --app-dir backend --reload
# 另开终端：python -m app.runtime.worker   （后台任务需要 Worker 消费）
```

迁移必须显式执行：

```powershell
Set-Location backend
$env:DATABASE_URL = "postgresql+asyncpg://career:career@localhost:5432/career"
python -m app.migration_runner
$env:AUTO_CREATE_SCHEMA = "false"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`migration_runner` 对全新数据库执行 `alembic upgrade head`；若检测到旧版通过 `create_all()` 建立的完整表结构，会先补齐新表并写入 Alembic revision，之后按迁移版本演进。开发环境默认 `AUTO_CREATE_SCHEMA=true` 方便临时 SQLite，**生产必须设为 `false`**。

前端：

```powershell
Set-Location frontend
pnpm install
pnpm dev
```

---

打开 `http://localhost:8000/docs`。可用接口：

- `GET /health/live`：进程存活检查
- `GET /health/ready`：PostgreSQL 与 Qdrant 就绪检查；依赖不可用时返回 HTTP 503 与 `status: degraded`，健康实例返回 200
- `POST /api/v1/evidence/text`：导入用户自述或导出的平台文本
- `POST /api/v1/evidence/file`：导入 PDF、DOCX、TXT 或 Markdown
- `POST /api/v1/evidence/media`：对图片 OCR 或音视频 ASR 后写入 Evidence
- `POST /api/v1/connectors/bilibili/import`：导入用户授权的 Bilibili JSON 导出
- `POST /api/v1/connectors/weibo/import`：导入用户授权的微博 JSON 或 CSV 导出
- `POST /api/v1/connectors/browser/import`：导入用户从 Bilibili、微博或抖音当前页面本地采集的 JSON；互动记录仅作兴趣线索
- `POST /api/v1/evaluation/run`：运行自定义人工标注评测集
- `POST /api/v1/evaluation/sample`：运行内置链路冒烟基准
- `POST /api/v1/evaluation/regression`：运行自定义数据集与阈值门禁
- `POST /api/v1/evaluation/regression/sample`：运行内置冻结回归门禁
- `POST /api/v1/evaluation/regression/benchmark`：运行多场景合成开发基准
- `GET /api/v1/evaluation/runs`：读取历史评测结果
- `GET /api/v1/observability/summary`：读取模型调用聚合指标
- `GET /api/v1/observability/calls`：读取最近模型调用明细
- `POST /api/v1/auth/register`：初始化用户 Owner Token（明文仅返回一次）
- `POST /api/v1/auth/tokens`：创建细粒度 Scope Token
- `GET /api/v1/privacy/{user_id}/export`：导出用户完整数据副本
- `GET /api/v1/privacy/{user_id}/audit`：读取隐私操作审计日志
- `DELETE /api/v1/privacy/{user_id}`：永久删除账号数据并返回匿名删除回执
- `DELETE /api/v1/evidence/{evidence_id}`：删除 Evidence、向量与画像引用
- `GET /api/v1/evidence`：按用户列出 Evidence
- `GET /api/v1/evidence/{evidence_id}`：查看单条 Evidence
- `POST /api/v1/profiles/{user_id}/rebuild`：重建结构化画像
- `GET /api/v1/profiles/{user_id}`：读取画像和证据引用
- `POST /api/v1/profiles/{user_id}/proposals`：生成画像变更草案（不直接写入）
- `POST /api/v1/profiles/proposals/{proposal_id}/decision`：确认或拒绝变更
- `POST /api/v1/jobs/analyze`：生成岗位匹配、缺口、学习路线和报告
- `POST /api/v1/reports`：基于画像和指定 JD 分析生成版本化职业报告
- `GET /api/v1/reports?user_id=...`：读取用户的职业报告版本
- `GET /api/v1/reports/{report_id}/markdown`：下载 Markdown 职业报告
- `POST /api/v1/chat`：通过 LangGraph 查询职业画像和证据。传入上次响应的 `thread_id` 可连续追问；响应中的 `messages` 返回该会话的完整历史消息，前端据此渲染多轮对话
- `GET /api/v1/evidence/search`：查看混合检索结果和诊断信息
- `POST /api/v1/evidence/reindex/{user_id}`：将用户 Evidence 重建到 Qdrant

评测与观测接口是实例级能力，不归属某个用户：在 `AUTH_MODE=required` 下调用 `/api/v1/evaluation/*` 与 `/api/v1/observability/*` 需要携带具备 `manage` Scope 的 Bearer Token；`disabled` 模式（默认）与无 Token 的 `optional` 模式放行，便于本机演示。

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
$env:DATABASE_URL = "postgresql+asyncpg://career:career@localhost:5432/career"
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

Docker Compose 已包含这个 HTTP 服务。先通过 `POST /api/v1/auth/register` 创建 Token，MCP 客户端连接 `http://localhost:8001/mcp` 时携带 `Authorization: Bearer <token>`。HTTP 模式按 Token 的 `subject` 限制 `user_id`，读取工具要求 `read`，导入、JD 分析和报告生成要求 `write`，`manage` 可覆盖这两类 Scope；所有工具调用都会写入同一张审计表。

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

Qwen3 Embedding 支持 Matryoshka 降维，因此这里默认使用 384 维；需要最高维度时可改为 `1024`，但应使用新 collection 或清空并重建现有 collection。

使用包含 Qwen 依赖和 Hugging Face 模型缓存卷的容器：

```powershell
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up --build
```

模型首次使用会下载约 0.6B 参数的 Embedding 与 Reranker 权重。导入 Evidence 时会自动写入 Qdrant；已有数据可调用：

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/evidence/reindex/demo-user
```

## 对话模型：API 与本地双路线

检索模型（`RETRIEVAL_*`）和生成模型（`AI_*`）相互独立。默认 `AI_PROVIDER=demo`，无需任何密钥即可运行，并使用确定性逻辑回退。

使用 DeepSeek API：

```powershell
$env:AI_PROVIDER = "deepseek"
$env:AI_BASE_URL = "https://api.deepseek.com"
$env:AI_API_KEY = "你的密钥"
$env:AI_MODEL = "deepseek-flash" # 按所用服务实际支持的模型 ID 调整
uvicorn app.main:app --app-dir backend --reload
```

Docker Compose 会把同名环境变量同时传入 API 和 MCP。建议把配置写入不会提交的 `.env`，然后重建服务：

```powershell
Copy-Item .env.example .env
# 编辑 .env：设置 AI_PROVIDER、AI_API_KEY 和 AI_MODEL
docker compose up -d --build api mcp web
.\scripts\docker-smoke.ps1
```

使用本地 Qwen（先用 vLLM、Ollama 等在 `8010` 端口暴露 OpenAI-compatible `/chat/completions` 接口，避开项目 MCP 的 `8001` 端口）：

```powershell
$env:AI_PROVIDER = "local"
$env:AI_BASE_URL = "http://localhost:8010/v1"
$env:AI_API_KEY = ""
$env:AI_MODEL = "Qwen/Qwen3-8B"
uvicorn app.main:app --app-dir backend --reload
```

`openai_compatible` 也可连接其他兼容服务。模型不可用、返回非法 JSON 或超时时，画像构建和对话会自动回退，不会影响核心闭环。
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

报告固定包含个人画像、核心能力、证据目录、就业方向、岗位匹配、能力缺口、学习路线和行动建议。DeepSeek/OpenAI-compatible 或本地 Qwen 可在证据边界内润色摘要与面试表达；未配置模型或调用失败时会生成确定性报告。每次生成都会创建新版本，不覆盖历史记录。若底层 Evidence 被删除，引用它的历史报告会标记为 `is_stale=true`，提醒用户重新生成。

Docker Compose 默认启用 PostgreSQL LangGraph checkpoint；本地 SQLite 测试可设置：

```powershell
$env:CHECKPOINT_BACKEND = "memory"
```

## 个人数据 Connector 与多模态导入

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

可选的 [`browser-helper/`](../browser-helper/README.md) 是 Chrome/Edge 本地页面采集工具：用户在 Bilibili、微博或抖音自己的页面登录、滚动加载，多次点击扩展汇总当前已加载的发布或互动条目，移除误采项并导出 JSON。工作台可逐条勾选，只有确认后才会写入 Evidence。扩展不读取 Cookie，也不提供后台同步。它不保证完整账号历史；点赞、收藏、关注仅作为兴趣线索，不直接推断技能。页面结构变化时可能漏项，详见[使用说明与限制](../browser-helper/README.md)。

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

仓库中的 [GitHub Actions 工作流](../.github/workflows/quality.yml) 配置了后端 lint、测试与回归门禁、前端 lint/build，以及 Docker 全栈 Smoke Test。

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

生产配置必须更换 pepper 并设置初始化密钥，否则服务会拒绝启动：

```text
AUTH_MODE=required
AUTH_TOKEN_PEPPER=使用密码管理器生成的高熵随机值
AUTH_REGISTRATION_SECRET=仅部署管理员持有的初始化密钥
```

初始化 Owner Token：

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

Scope 包括 `read`、`write`、`export`、`delete`、`manage`。数据库仅保存带 pepper 的 SHA-256 Token 哈希；导出文件不包含 Token 或哈希。删除 Evidence 时会同时删除 Qdrant 向量、移除 Profile 引用，并保存不含 Evidence 原文的审计事件。

整账号删除要求 `delete` 或 `manage` Scope，会删除 Evidence、画像、JD、报告、画像修正、审计事件、对话线程及其全部消息、LangGraph checkpoint、Qdrant 向量和全部 Token。删除完成后原 Token 立即失效；系统仅保留匿名回执，其中包含带 pepper 的不可逆用户哈希、删除数量、向量/会话清理状态和时间，不保留用户 ID 或 Evidence 原文。

本地 stdio MCP 被视为部署边界内的可信接口，不读取 HTTP Bearer Token；生产部署时不要向不受信任用户暴露 stdio 进程。对外服务必须使用启用 Bearer Token 的 Streamable HTTP，并将 `AUTH_TOKEN_PEPPER` 替换为随机密钥。

生产配置模板会强制 API 鉴权并检查 PostgreSQL 密码、Token Pepper 和 Registration Secret 是否存在：

```powershell
Copy-Item .env.production.example .env
# 编辑 .env，将全部 replace-with-* 值替换为真实随机值和模型配置
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

`.env`、本地数据库、上传内容和模型缓存均已在 `.gitignore` 中排除。公开部署仍需在容器前配置 HTTPS 反向代理，并在网络层限制 PostgreSQL 与 Qdrant 端口。


