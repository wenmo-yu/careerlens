# CareerLens · 个人职业画像与求职决策 Agent

> 从个人经历中找到证据，再用证据回答“我适合这个岗位吗、还缺什么、下一步怎么做？”

CareerLens 将用户授权的简历、自述和个人平台导出内容整理为 **Evidence**，构建可持续更新的结构化职业画像。输入目标岗位 JD 后，系统将每项要求与带证据引用的画像逐项对照，给出岗位匹配、能力缺口、学习路线和职业报告；用户还能通过 Career Copilot 检索原始证据、追问每一项结论。

**开源版本可在本机运行完整业务流程。** 基础 Docker 模式已用 PostgreSQL、Qdrant、API、MCP 和 Web 验证；默认使用确定性演示模型与轻量检索 Provider。DeepSeek/OpenAI-compatible、本地 Qwen、OCR/ASR 提供可选接入代码和配置，实际效果取决于所用模型与运行环境。

[功能流程](#核心使用流程) · [系统架构](#系统架构) · [快速启动](#快速启动) · [验证结果](#已验证的范围) · [技术文档](docs/README.md) · [评测口径](eval/README.md)

## 界面预览

![CareerLens 职业决策工作台首页](docs/assets/overview.jpg)

截图来自本地 Docker 环境，使用虚构资料和默认 Demo 模型。[查看画像、岗位匹配、报告与对话的完整界面展示](docs/showcase.md)。

## 核心使用流程

| 步骤 | 在 Web 工作台中操作 | 系统会展示什么 |
| --- | --- | --- |
| 1. 导入经历 | 粘贴自述、上传简历，或导入授权导出的个人内容 | 带来源、时间与 ID 的 Evidence |
| 2. 构建画像 | 点击“导入并生成画像” | 技能、兴趣、经历等结构化条目，以及置信度和证据引用 |
| 3. 分析岗位 | 粘贴目标 JD，设置每周可投入时间 | 每项 Requirement 的 strong / partial / gap 判断、对应证据与学习路线 |
| 4. 生成报告 | 点击“生成职业报告” | 八章节、可下载 Markdown、保留历史版本的职业报告 |
| 5. 追问结论 | 在 Career Copilot 中询问“为什么推荐这个方向？” | 多轮回答、检索诊断与可展开的原始证据 |
| 6. 修正记忆 | 提出新的求职偏好并确认变更草案 | 用户批准后写入长期画像的修正记录 |

首页预填了**虚构**个人经历与 JD，可在无需 API Key 的默认配置下体验完整流程。真实个人资料仅应在获得授权并采取适当保护时导入。

## 为什么这样设计

普通求职助手容易给出流畅但缺少依据的建议。CareerLens 把“证据是否足以支持结论”放在输出链路中：

```text
用户授权内容 → 标准化 Evidence → 带证据 ID 的 Profile
                                     ↓
目标岗位 JD → 逐项 Requirement → 带证据引用的画像对照
                                     ↓
                          Strong / Partial / Gap
                                     ↓
                      学习路线、报告与可追问的回答
```

- **结论可追溯**：画像条目和岗位匹配保留 Evidence ID；缺少证据时显示能力缺口，不把推测写成已有经历。
- **长期记忆可纠正**：用户的偏好修正先成为草案，确认后才写入画像，避免对话中的一句话静默改变长期资料。
- **检索与生成解耦**：Qdrant 负责个人证据的 Dense + Sparse 双路检索、RRF 融合与二阶段重排；生成模型可以切换为 API 或本地服务。
- **个人数据可控**：提供 Scope Token、数据导出、单条 Evidence 删除与整账号清理，并为敏感操作保留不含原文的审计记录。

## 系统架构

```mermaid
flowchart TD
    U[用户授权数据<br/>简历 / 自述 / 平台导出] --> I[解析、标准化与分块]
    I --> E[(PostgreSQL<br/>Evidence 与 Structured Profile)]
    I --> Q[(Qdrant<br/>Dense + Sparse 索引)]
    W[Next.js 职业决策工作台] --> A[FastAPI 异步 API]
    C[MCP 客户端] --> M[MCP Tools / Resources / Prompts]
    M --> S[共享业务服务]
    A --> S
    S --> E
    S --> Q
    S --> G[LangGraph Career Copilot]
    S --> J[JD 匹配 / Skill Gap / Learning Path]
    S --> R[版本化职业报告]
    G --> E
    G --> Q
    J --> E
    J --> R
    L[Demo / DeepSeek / OpenAI-compatible / 本地 Qwen] --> G
    L --> R
    P[(PostgreSQL Checkpoint)] --> G
```

PostgreSQL 是业务数据源，Qdrant 是可从 Evidence 重建的检索索引。基础 Compose 用独立 migration job 执行 Alembic 迁移；API 与 MCP 共用业务服务和数据权限规则。更多实现细节见[技术文档导航](docs/README.md)：架构、数据模型、Agent 与检索、接口安全、评测和运维。

## 技术栈与实现范围

| 层 | 技术 | 在项目中的用途 |
| --- | --- | --- |
| Web | Next.js 16、React 19、TypeScript | 导入、画像、岗位分析、报告、对话和评测工作台 |
| API / 数据 | FastAPI、Pydantic、SQLAlchemy Async、PostgreSQL、Alembic | 异步业务接口、持久化与版本化迁移 |
| Agent / Memory | LangGraph、PostgreSQL Checkpoint | 意图理解、个人证据检索、回答生成与多轮会话 |
| Evidence RAG | Qdrant、Dense + Sparse、RRF、Reranker Provider | 按用户隔离的证据检索、融合与重排 |
| 模型 | 确定性 Demo、DeepSeek / OpenAI-compatible API、本地 Qwen 接口 | 无密钥可复现；按需接入真实推理服务 |
| 数据接入 | PDF / DOCX / TXT / Markdown、Bilibili JSON、微博 JSON/CSV | 用户主动上传和授权导出，不依赖登录态爬取 |
| 可选多模态 | PaddleOCR、Faster-Whisper | 图片文字与音视频转录，需额外安装模型依赖 |
| 工具与交付 | MCP Python SDK、Docker Compose、GitHub Actions | 可复用工具接口、容器部署和质量门禁 |

### 关键代码导航

| 想看什么 | 从这里开始 |
| --- | --- |
| 前端完整操作流 | [`frontend/app/page.tsx`](frontend/app/page.tsx) |
| Evidence 归一化与业务写入 | [`backend/app/services/evidence.py`](backend/app/services/evidence.py)、[`backend/app/ingestion/`](backend/app/ingestion/) |
| 画像构建与人工确认修正 | [`backend/app/services/profile.py`](backend/app/services/profile.py)、[`backend/app/services/profile_updates.py`](backend/app/services/profile_updates.py) |
| Qdrant 双路检索与重排 | [`backend/app/retrieval/qdrant_store.py`](backend/app/retrieval/qdrant_store.py) |
| LangGraph 对话流程 | [`backend/app/graph/career.py`](backend/app/graph/career.py) |
| JD 分析与报告生成 | [`backend/app/services/jobs.py`](backend/app/services/jobs.py)、[`backend/app/services/reports.py`](backend/app/services/reports.py) |
| MCP 接口与权限 | [`backend/app/mcp/server.py`](backend/app/mcp/server.py)、[`backend/app/security/auth.py`](backend/app/security/auth.py) |
| 评测与可重复验收 | [`backend/app/evaluation/`](backend/app/evaluation/)、[`scripts/docker-smoke.ps1`](scripts/docker-smoke.ps1) |

## 已验证的范围

| 验证项 | 当前结果 | 边界 |
| --- | --- | --- |
| 后端自动化测试 | 40 项通过 | 以 SQLite 内存数据库运行的单元/API 测试 |
| 前端检查 | ESLint 与 production build 通过 | 属于静态检查和构建验证 |
| Docker 全栈验收 | 迁移、健康检查及 Evidence → 画像 → JD → 报告 → 对话成功 | 使用本机 PostgreSQL、Qdrant、API、MCP、Web 和 Demo 模型 |
| 检索与 MCP | 烟测命中 Qdrant；MCP 未授权请求返回 401、合法 Token 可初始化 | 默认 Embedding 为 Hash Provider、重排为 Lexical Provider |
| 开发回归集 | 10 个合成场景、40 条 Evidence、20 个检索问题 | 只用于发现代码回归，不能当作真实业务准确率 |

上述结果来自本地验收；GitHub Actions 工作流也已配置。它们验证了默认链路和开发回归集，不代表不同模型、硬件或真实用户数据下的效果。完整评测口径见[评测文档](eval/README.md)。

### 项目背景

CareerLens 来自一个更早的本科求职分析项目原型。原型曾获第十七届“挑战杯”广东大学生课外学业科技作品竞赛一等奖、第十四届“挑战杯”广东大学生创业计划竞赛银奖，以及中国国际大学生创新大赛广东省分赛铜奖。**本仓库的 LangGraph、MCP、长期画像和 Evidence RAG 架构属于后续重构**；上述奖项属于早期原型，不是当前代码版本的获奖认证。

## 快速启动

需要 Docker Desktop（或可用的 Docker Engine + Compose）。在仓库根目录执行：

```powershell
docker compose up -d --build
.\scripts\docker-smoke.ps1
```

首次构建需要下载容器镜像和 Python/Node 依赖。`docker-smoke.ps1` 会创建一次虚构账号，走完 Evidence、画像、JD、报告、对话、检索、回归评测与 MCP 鉴权，然后删除测试账号数据；成功时输出 `status : passed`。脚本需要 PowerShell 7 或 Windows PowerShell 5.1。

访问：

- Web：`http://localhost:3000`
- API 文档：`http://localhost:8000/docs`
- MCP Streamable HTTP：`http://localhost:8001/mcp`
- Qdrant：`http://localhost:16333/dashboard`（可通过 `QDRANT_HTTP_PORT` 修改宿主机端口；容器内仍使用 `6333`）

结束本地演示时执行 `docker compose down`；命名卷中的 PostgreSQL 和 Qdrant 数据会保留。不要在需要保留数据时使用 `docker compose down -v`。

也可以不使用 Docker，分别启动开发服务（Python 3.11+、Node.js 20.9+）：

```powershell
Copy-Item .env.example .env
docker compose up -d
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".\backend[dev]"
uvicorn app.main:app --app-dir backend --reload

Set-Location frontend
pnpm install
pnpm dev
```

Docker Compose 会先运行一次 `migrate` 服务，再启动 API 与 MCP。非 Docker 部署应在发布阶段执行：

```powershell
Set-Location backend
$env:DATABASE_URL = "postgresql+asyncpg://career:career@localhost:5432/career"
python -m app.migration_runner
$env:AUTO_CREATE_SCHEMA = "false"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`migration_runner` 对全新数据库执行 `alembic upgrade head`；若检测到旧版本通过 SQLAlchemy `create_all()` 建立的完整表结构，会先补齐新增表并写入 Alembic revision，之后全部按迁移版本演进。开发环境默认 `AUTO_CREATE_SCHEMA=true` 以方便临时 SQLite；生产环境必须设为 `false`。

打开 `http://localhost:8000/docs`。可用接口：

- `GET /health/live`：进程存活检查
- `GET /health/ready`：PostgreSQL 与 Qdrant 就绪检查
- `POST /api/v1/evidence/text`：导入用户自述或导出的平台文本
- `POST /api/v1/evidence/file`：导入 PDF、DOCX、TXT 或 Markdown
- `POST /api/v1/evidence/media`：对图片 OCR 或音视频 ASR 后写入 Evidence
- `POST /api/v1/connectors/bilibili/import`：导入用户授权的 Bilibili JSON 导出
- `POST /api/v1/connectors/weibo/import`：导入用户授权的微博 JSON 或 CSV 导出
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
- `POST /api/v1/chat`：通过 LangGraph 查询职业画像和证据
- `GET /api/v1/evidence/search`：查看混合检索结果和诊断信息
- `POST /api/v1/evidence/reindex/{user_id}`：将用户 Evidence 重建到 Qdrant

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

微博 Connector 支持 UTF-8 JSON 和 CSV。JSON 可使用根数组，或 `statuses`、`posts`、`weibo`、`items` 数组；CSV 支持 `微博正文` / `text`、`发布时间` / `created_at`、`话题` / `topics`、`微博链接` / `url` 等中英文列名。正文中的简单 HTML 会被清洗，话题和转发内容会进入 Evidence；缺少微博 ID 时使用发布时间与正文生成稳定内容指纹，因此重新排序后重复导入仍能正确跳过。示例见 [`examples/weibo-export.example.json`](examples/weibo-export.example.json)。

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

## 评测与模型观测

评测不使用 LLM-as-a-Judge，而是与冻结标签中的画像、Evidence 和 JD 状态比较。网页和 CI 默认运行 v2 合成开发基准：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/evaluation/regression/benchmark
```

v2 包含 10 个场景、40 条 Evidence、20 个检索问题，并覆盖中英文别名、strong / partial / gap、纯缺口和无技能干扰样本。它用于发现代码回归，不是真实用户分布，因此即使指标为 100% 也不能直接写成业务准确率。自定义数据集格式见 [`eval/README.md`](eval/README.md)。

真实 LLM 调用会记录 operation、provider、model、成功状态、延迟和 Token，不记录 Prompt、API Key 或个人 Evidence 原文。配置每百万 Token 单价后可计算成本：

```text
AI_INPUT_PRICE_PER_MILLION=0
AI_OUTPUT_PRICE_PER_MILLION=0
```

运行冻结回归门禁（任一指标退化时进程返回 `1`）：

```powershell
Set-Location backend
python -m app.evaluation.cli `
  --dataset app/evaluation/dev_benchmark_v2.json `
  --baseline ../eval/baselines/careerlens-dev-benchmark-v2.json
```

仓库中的 [GitHub Actions 工作流](.github/workflows/quality.yml) 配置了后端 lint、测试与回归门禁、前端 lint/build，以及 Docker 全栈 Smoke Test。

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

整账号删除要求 `delete` 或 `manage` Scope，会删除 Evidence、画像、JD、报告、画像修正、审计事件、对话线程、LangGraph checkpoint、Qdrant 向量和全部 Token。删除完成后原 Token 立即失效；系统仅保留匿名回执，其中包含带 pepper 的不可逆用户哈希、删除数量、向量/会话清理状态和时间，不保留用户 ID 或 Evidence 原文。

本地 stdio MCP 被视为部署边界内的可信接口，不读取 HTTP Bearer Token；生产部署时不要向不受信任用户暴露 stdio 进程。对外服务必须使用启用 Bearer Token 的 Streamable HTTP，并将 `AUTH_TOKEN_PEPPER` 替换为随机密钥。

生产配置模板会强制 API 鉴权并检查 PostgreSQL 密码、Token Pepper 和 Registration Secret 是否存在：

```powershell
Copy-Item .env.production.example .env
# 编辑 .env，将全部 replace-with-* 值替换为真实随机值和模型配置
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

`.env`、本地数据库、上传内容和模型缓存均已在 `.gitignore` 中排除。公开部署仍需在容器前配置 HTTPS 反向代理，并在网络层限制 PostgreSQL 与 Qdrant 端口。


