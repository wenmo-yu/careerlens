# 常见问题

按你在哪一步卡住分类。每项是「看到什么 → 怎么确认 → 怎么恢复」。查之前先确认你用的是**默认 Demo 栈**（没改配置、没接真实模型）——大多数入门问题都出在这三件事上：目录不对、服务没起来、后台 Worker 没运行。

## 启动与安装

### 执行 `docker compose` 提示找不到命令

- **看到什么**：`docker: command not found` 或「无法识别 docker」。
- **怎么确认**：终端运行 `docker version` 和 `docker compose version`，看有没有版本号输出。
- **怎么恢复**：按[第 01 篇的本机准备](01-quickstart.md#步骤-1本机准备按系统选)安装 Docker Desktop / Engine；装完**重新打开终端**再试（PATH 要刷新）。

### `Cannot connect to the Docker daemon`

- **看到什么**：连不上 Docker 引擎，或 `docker version` 只有 Client 没有 Server 部分。
- **怎么确认**：打开 Docker Desktop，看引擎是否处于 running；再跑一次 `docker version` 看有没有 `Server:` 段。
- **怎么恢复**：启动 Docker Desktop 并等到引擎就绪；Windows 上若提示 WSL 2 / 虚拟化问题，按 Docker 官方安装指南检查。Linux 上确认 Docker Engine 服务已启动。

### `docker compose up` 报端口被占用

- **看到什么**：`port is already allocated` 或 `address already in use`。
- **怎么确认**：看报错里的端口号。默认 Web 3000、API 8000、MCP 8001、PostgreSQL 5432、Qdrant 16333/16334。
- **怎么恢复**：Qdrant 的两个端口可用环境变量改，例如在 PowerShell 里先 `$env:QDRANT_HTTP_PORT=26333; $env:QDRANT_GRPC_PORT=26334` 再启动；其他端口需要先停掉占用它的程序。改端口后记得同步改访问地址。

### 首次构建特别慢

- **看到什么**：拉镜像、装依赖卡很久。
- **怎么确认**：看终端是否在下载镜像 / building，而不是报错。
- **怎么恢复**：属正常现象，等它完成即可。后续启动会快很多。

### `migrate` 服务没成功

- **看到什么**：业务接口连不上库，或 `docker compose ps -a` 里 `migrate` 不是 `Exited (0)`。
- **怎么确认**：`docker compose logs migrate` 看具体报错。
- **怎么恢复**：迁移在 API 之前执行；若跳过 Compose 手动启动，先跑 `python -m app.migration_runner`。用 Compose 时通常是数据库还没就绪，重试 `docker compose up -d` 即可。

### 想停止服务

- **看到什么**：想关掉本机环境。
- **怎么确认**：正常停止不会删数据。
- **怎么恢复**：用 `docker compose down`（**不要加 `-v`**，否则会删除数据库和向量数据卷）。

## 就绪检查与 API

### 就绪接口返回 503 或 `degraded`

- **看到什么**：打开 `http://localhost:8000/health/ready` 不是 `status: ok`。
- **怎么确认**：看返回里的 `checks` 字段，是 `database` 还是 `qdrant` 显示 `unavailable`。
- **怎么恢复**：对应服务没起来。用 `docker compose ps` 看 postgres / qdrant 是否 healthy，必要时 `docker compose logs postgres`（或 `qdrant`）查原因。注意健康接口是 `/health/ready`，**没有** `/api/v1` 前缀。

### `/docs` 里点 Execute 报 422

- **看到什么**：Swagger 返回字段校验错误。
- **怎么确认**：对照接口文档看必填字段；岗位分析的 `jd_text` 至少 10 个字符，字段类型和长度都有要求。
- **怎么恢复**：把请求体的字段名、类型填对；证据接口返回的是 `items` 数组，取 ID 用 `items[0].id`，岗位匹配看 `matches` 里的 `status` 与 `evidence_ids`。

### 工作台点了没反应

- **看到什么**：点「导入并生成画像」「分析匹配度」后没变化。
- **怎么确认**：看页面提示条，再看 `docker compose ps` 里 worker 是否在跑；后台报告类操作要等任务成功。
- **怎么恢复**：等任务完成；若一直 queued，见下面「后台任务」。

## 数据

### 同一段内容导入两次，担心重复

- **看到什么**：重复导入同一份自述。
- **怎么确认**：再看一次证据列表，同一个用户 + 同一段规范化文字会复用同一个 Evidence ID，不会新建。
- **怎么恢复**：这是设计行为，不用处理。重复内容会把新来源追加到证据的来源信息里，避免虚增置信度。

### 「收藏」被算成了技能

- **看到什么**：导入一段写着「收藏了 Kubernetes 教程」的普通自述后，画像里出现了 Kubernetes 技能。
- **怎么确认**：看你导入的 `source_type`。**只有作为带 `preference_signal` 标记的浏览器互动记录导入时，收藏才会被排除在技能外**；当普通文本导入，默认 Demo 会按关键词把它当成技能。
- **怎么恢复**：这就是 Demo 的已知局限——入门阶段不靠它做真实判断。想看正确的处理方式，用工作台的浏览器记录导入入口（发布内容按自报处理，点赞/收藏/关注只作兴趣线索），或在阶段 5 的对照实验里比较两种导入结果。

### 找不到某条结论的原始证据

- **看到什么**：回答或报告里引用了一个 ID，但不知道原文在哪。
- **怎么确认**：从报告的证据目录或引用的 evidence_id 回查 `/api/v1/evidence/{id}`；Wiki 页里 `c000` 是编译期短句柄，落库时已解析为稳定 ID。
- **怎么恢复**：若确实没有支撑证据，结论应按「证据不足」处理，不要手动补一条自述来「凑证据」。

## 后台任务

### 任务一直 queued

- **看到什么**：提交报告 / 编译后进度不动。
- **怎么确认**：`docker compose ps` 看 worker 服务是否存在且健康。
- **怎么恢复**：后台任务靠独立 Worker 执行。Compose 默认会起 Worker；若手动启动，另跑 `python -m app.runtime.worker`。没启动 Worker 时任务不会自己跑。

### 重复提交会不会重复执行

- **看到什么**：担心网络重试导致生成两次报告。
- **怎么确认**：用相同的 `Idempotency-Key` 再提交一次，看返回的 run ID 是否和第一次相同。
- **怎么恢复**：相同键返回同一个任务，不会重复执行；这就是幂等键的作用。

### 刷新页面后进度丢失

- **看到什么**：中途刷新，进度条回到起点。
- **怎么确认**：用任务 ID 查 `/api/v1/runs/{run_id}/events`，看事件序号是否递增。
- **怎么恢复**：进度按事件序号续看，刷新后能接着显示。若查不到任务，用任务 ID 而非页面状态恢复。取消后重跑是一个新任务，**不是接着上一次的模型输出继续生成**。

## 模型与数据

### 要不要申请 API Key

- **看到什么**：教程里提到真实模型接入。
- **怎么确认**：默认 Compose 使用 Demo 模型和轻量检索，`AI_PROVIDER=demo`、`RETRIEVAL_PROVIDER=hash`。
- **怎么恢复**：入门全程不需要 API Key 或 GPU。真实模型（DeepSeek / OpenAI-compatible / 本地 Qwen、OCR/ASR）是进阶可选内容，效果取决于模型和环境。

### Demo 分数能当真实准确率吗

- **看到什么**：工作台或评测页有一个匹配分数。
- **怎么确认**：看评测口径说明。
- **怎么恢复**：不能。默认分数来自规则权重与合成数据，只说明默认链路稳定，不代表真实用户或真实岗位的准确率。

### 导出了数据，想彻底删除

- **看到什么**：想收回自己的数据。
- **怎么确认**：工作台的隐私区提供「下载 JSON 数据副本」、删除单条 Evidence、以及输入用户 ID 确认后永久删除账号。
- **怎么恢复**：永久删除会清理数据库、向量、对话状态和令牌，只保留不含原文的审计记录。删除前先下载数据副本留档。

## 提问模板

自查后仍解决不了，提 Issue 时带上这些信息（**遮掉密钥、账号和真实资料**）：

```text
篇名与卡住的步骤：
操作系统与版本：
执行的完整命令：
预期输出：
实际输出（原样贴）：
是否改过配置 / 是否默认 Demo：
```
