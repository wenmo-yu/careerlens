# 01 · 从零跑通

**目标**：在本机启动 CareerLens 完整闭环，亲手走一遍 `输入 → Evidence → 画像 → 岗位匹配 → 报告 → 对话`，建立对整个系统数据流的直觉。

**前置**：Docker Desktop 或（Docker Engine + Compose v2）；无需 API Key、无需 GPU。

**预计耗时**：首次构建含镜像下载约 10–20 分钟，之后启动约 1 分钟。

---

## 步骤 1：启动服务

在仓库根目录：

```powershell
docker compose up -d --build
```

Compose 会依次拉起 PostgreSQL、Qdrant、一次性 migration job、API、MCP、Worker 和 Web。等所有服务就绪：

```powershell
docker compose ps
```

`migrate` 服务应已退出（`Exited (0)`），其余服务为 `Up`。

> 迁移先于 API 执行。若你跳过 Compose 手动启动，必须先跑 `python -m app.migration_runner`，否则会连到未建表的数据库。

## 步骤 2：确认部署正常

```
http://localhost:8000/docs        API 文档（Swagger）
http://localhost:3000/workspace   交互工作台
```

打开 `/docs`，找到 `GET /api/v1/health/ready`。依赖都正常时返回 `{"status": "ok"}`；PostgreSQL 或 Qdrant 不可用时返回 HTTP 503 与 `status: degraded`。

## 步骤 3：用合成资料走一遍业务闭环

打开工作台 `http://localhost:3000/workspace`。页面已预填**虚构**资料，按顺序：

1. 点击「导入并生成画像」——观察左侧出现带来源和 ID 的 Evidence，右侧出现技能/兴趣等画像条目。
2. 在分析岗位区粘贴一段 JD、设置每周时间，点击分析——看到每条要求被判为 `strong / partial / gap`。
3. 点击「生成职业报告」——得到八章节报告，可下载 Markdown，并保留版本。
4. 在 Career Copilot 里问"为什么推荐这个方向？"——回答下方有检索诊断，可展开原始 Evidence。
5. 试一次「后台任务」：提交一个报告生成，观察进度条，中途刷新页面——进度能从断点续看。

> 工作台的预填内容是虚构的。真实个人资料只应在获得授权并采取保护措施时导入。

## 步骤 4：用 API 重做一次（理解数据流）

在 `/docs` 里依次调用，观察每一步的返回：

```powershell
# 1. 写入一条自述 → 得到带 id 的 Evidence
POST /api/v1/evidence/text
{
  "user_id": "learner",
  "source_type": "self_statement",
  "source_name": "goal",
  "content": "我希望从事 AI Agent 与 LLM 应用开发，熟悉 Python 和 FastAPI。"
}

# 2. 构建画像 → 画像条目带 evidence_ids
POST /api/v1/profiles/learner/rebuild
GET  /api/v1/profiles/learner

# 3. 分析岗位 → 每条 requirement 带 status 与证据
POST /api/v1/jobs/analyze
{ "user_id": "learner", "title": "AI Agent 开发",
  "jd_text": "Python FastAPI LangGraph RAG", "weekly_hours": 10 }

# 4. 生成报告（用第 3 步返回的 job_analysis_id）
POST /api/v1/reports
{ "user_id": "learner", "job_analysis_id": "<上一步的 id>" }

# 5. 对话，切换检索模式
POST /api/v1/chat
{ "user_id": "learner", "message": "我适合什么方向？", "mode": "hybrid" }
```

**观察重点**：第 2 步画像条目里的 `evidence_ids` 指向第 1 步的证据；第 3 步每条要求也带证据。这就是整个项目的核心不变量——**结论必须落到证据**。

## 步骤 5：提交一个后台任务并观察事件

```powershell
POST /api/v1/runs
{
  "user_id": "learner",
  "operation": "report",
  "input": { "job_analysis_id": "<岗位分析 id>" },
  "requires_confirmation": false
}
```

返回 `202` 和 run id。随后：

```
GET /api/v1/runs/<run_id>        查看状态（queued → running → succeeded）
GET /api/v1/runs/<run_id>/events 查看有序事件
GET /api/v1/runs/<run_id>/stream SSE 进度流
```

重复用同一个 `Idempotency-Key` 提交，会返回同一个 run，不会重复执行。

---

## 验收清单

做到以下各点，算完成本篇：

- [ ] `docker compose ps` 显示所有服务正常，migration 已退出(0)
- [ ] `/api/v1/health/ready` 返回 `status: ok`
- [ ] 工作台走通导入→画像→岗位→报告→对话五步
- [ ] 能说清楚 `Evidence ID` 在画像和岗位匹配里起什么作用
- [ ] 提交后台 run 并看到它从 queued 走到 succeeded
- [ ] 刷新页面后进度可续看

## 常见问题

- **端口冲突**：Qdrant 宿主机端口可用 `QDRANT_HTTP_PORT` 改；容器内仍用 6333。
- **首次构建很慢**：需要下载 PostgreSQL、Qdrant 镜像与 Python 依赖，属正常。
- **后台任务一直 queued**：确认 Worker 服务已启动（`docker compose ps` 里有 worker）；非 Compose 手动启动时要另跑 `python -m app.runtime.worker`。
- **想保留冒烟数据**：`docker-smoke.ps1` 默认清理测试账号，加 `-KeepData` 保留。

## 下一步

你已经看到了系统的全貌。接下来进入[第 02 篇：数据模型](02-data-model.md)——理解支撑这一切的三张核心表。后续篇章（解析层、检索 Agent、知识组织、后台运行时）见[教程总览](README.md)。
