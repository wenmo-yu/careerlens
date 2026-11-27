# ADR 0002：API 兼容基线

- 状态：Accepted（当前 API 快照）
- 日期：2026-11-27
- 阶段：M0–M3
- 相关规范：V4 §9.2、§9.3、§18.1
- 相关契约：[`api-baseline-v0.4.0.json`](../../contracts/api-baseline-v0.4.0.json)、[`openapi-v0.4.0.json`](../../contracts/openapi-v0.4.0.json)
- 参考测试：T02、T03、T10、T25、T33

## 背景

Desktop 与 Web 必须复用同一业务 API。V4 新增 `/runtime/capabilities`、`/agent/*` 等路由是扩展，不是替换现有 `/api/v1`。如果实现时边写边改老接口，会造成旧 Web 客户端、桌面壳和 Worker 两套契约，无法证明同一 Run ID 与同一报告在两端一致。

## 决定

### 基线事实

- 快照生成提交：`91cfae2278123cdaf9bd82a1a89403f731c846e7`。
- 该提交的 `backend/`、`frontend/`、`docs/` 子树对象 ID 与 V4 设计基线 `43c67d3b01540ba80c00c17efd483336a08c2426` 相同。
- FastAPI 应用版本 `0.4.0`；OpenAPI `3.1.0`；79 个路径、88 个操作、78 个 schema。
- 现有路径包含 `/health/live`、`/health/ready`、`/api/v1/auth/me`、`/api/v1/chat`、`/api/v1/runs*`、Evidence、画像、岗位、报告、Wiki、隐私、评测与 MCP 相关接口。完整清单以机器可读快照为准，不在 ADR 中手抄。
- Run 流继续复用 `GET /api/v1/runs/{run_id}/stream`、`after_seq` 与 `Last-Event-ID` 契约；`/health/ready` 只表示 API 与关键依赖就绪，不能单独证明 Worker、Scheduler 或 Agent runtime 可用。

### 兼容规则

1. M0–M9 只新增 method/path、可选请求字段或诊断字段；不得改变现有 method/path、必填请求字段、成功状态码和 SSE 游标语义。
2. 新增能力先更新 `contracts/` 与 ADR，再实现调用方；不允许前端按假接口开发后反向改后端。
3. 所有新增接口由服务端 principal 推导用户与工作区，不信任请求体里的 `user_id`、`workspace_id` 或工具参数。
4. 新增 `/runtime/capabilities` 用于报告 API、事件、引擎版本和能力；它是发现接口，不替代 `/health/ready` 或 `/auth/me`。
5. 身份、工作区、审批、Run 与产物接口必须明确区分 401、403、409、422、429、503；未知能力只提示升级，核心身份/Run 契约不满足时拒绝连接。
6. 旧 `/chat` 保持兼容并作为评估基线；新增 durable agent operation 与它共用主线约束或使用显式不同 session，排队输入不能提前进入当前 Run 上下文。

### 版本记录（第一步实测）

| 层 | 值 | 来源 |
| --- | --- | --- |
| CareerLens backend / frontend | `0.4.0` / `0.4.0` | `backend/pyproject.toml`、`frontend/package.json` |
| OpenAPI | `3.1.0` | 当前 FastAPI 应用导出 |
| Python 最低版本 / CI 版本 / 本机版本 | `>=3.11` / `3.12` / `3.13.14` | `backend/pyproject.toml`、`.github/workflows/quality.yml`、本机 `python --version` |
| Node CI / 本机 | `22` / `22.22.2` | `.github/workflows/quality.yml`、本机 `node --version` |
| pnpm CI 主版本 / 本机 | `10` / `10.9.7` | CI 配置、本机 `pnpm --version` |
| Next.js / React / TypeScript 锁定版本 | `16.4.6` / `19.3.0` / `5.9.3` | `frontend/pnpm-lock.yaml`；CI 使用 `pnpm install --frozen-lockfile`，因此这就是 CI 版本 |
| FastAPI / LangGraph / Qdrant client 锁定版本 | `0.143.2` / `1.2.15` / `1.15.1` | `backend/uv.lock` |
| SQLAlchemy / pydantic-settings / pytest 锁定版本 | `2.1.4` / `2.16.3` / `9.2.0` | `backend/uv.lock` |
| 本机隔离环境实测版本 | FastAPI `0.165.0`、LangGraph `1.2.24`、SQLAlchemy `2.1.9`、Qdrant client `1.15.1`、pydantic-settings `2.16.3`、pytest `9.2.0` | `pip install -e ".[dev]"` 后导入版本 |

**版本口径注意**：当前后端 CI 使用 `pip install -e ".[dev]"`，从 `pyproject.toml` 的范围约束解析依赖，并不执行 `uv sync`，因此 `uv.lock` 不是 CI 的事实版本来源；本机隔离环境也已证明解析结果可能与锁文件不同。V4 后续必须把“锁文件版本”和“实际安装版本”分开记录，并在打包原型中固定运行时版本。

## 替代方案与取舍

- **为 Desktop 另建一套 API**：可短期绕过兼容问题，但会产生两套身份、Run 与产物事实，违反 V4 唯一所有权，故不采用。
- **让 Desktop 直接读业务库**：减少 HTTP 跳转，但绕过鉴权、事务、审计和工作区隔离，禁止。
- **逐步替换旧 `/chat`**：M3 之前保持旧接口可回归；新入口只以新增 operation 接入，避免旧客户端静默失效。

## 风险与待验证项

- 目前没有 Endpoints 级 Desktop 兼容矩阵；M1 必须记录同主体、同 Run ID、同报告 ID 的双端实测结果（T02）。
- 反代路径、TLS、重定向和远端凭证绑定 origin 尚未验证；连接地址必须拆分服务根与 API prefix。
- 新增 `/api/v1/agent/*` 路径尚未落地；落地前需在基线 OpenAPI 上检查冲突。
- 发布兼容下限尚未确定；V4 要求以实际验收过的 Web/API 发布为准，不能把当前工作树当作已发布稳定基线。

## 验证与回滚

- 每次 API 变更从当前应用重新导出 OpenAPI，与 `contracts/openapi-v0.4.0.json` 对比；差异必须进入本 ADR 和 API 基线 JSON。
- M3/M4 新增的会话、审批与 runtime 诊断路径只增不改，清单见 [`agent-api-additions-v1.json`](../../contracts/agent-api-additions-v1.json)；内部网关路由不进入公开 schema。
- M1 验证 Web/桌面同一主体与 Run ID；M3 验证新旧 chat 不双写；CI 保留现有 Web/API 回归。
- 若发现破坏性变化，停止合并并回退调用方与 schema；不得通过改测试预期掩盖差异。
