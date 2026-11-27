# ADR 0010：M3 持久 Agent 运行契约与自研 Runner 实装

- 状态：Accepted（M3 只读闭环已落地；真实模型与写工具未开放）
- 日期：2026-11-27
- 相关契约：[`agent-runtime-v1.json`](../../contracts/agent-runtime-v1.json)、[`agent-api-additions-v1.json`](../../contracts/agent-api-additions-v1.json)、[`runtime-jsonl-v1.methods.json`](../../contracts/runtime-jsonl-v1.methods.json)
- 相关代码：`backend/app/models/agent.py`、`backend/app/runtime/agent/`、`backend/app/api/routes/agent.py`、`backend/app/api/routes/agent_internal.py`

## 背景

M0 只证明了自研状态机和 JSONL 帧可行，但没有持久会话、消息、ACK/结算分层和真正的 CLI 进程。M3 要求“可启动一个自研主会话，真实流式工具调用和引用；请求 ACK 与结算分开；重连恢复历史；旧任务不重复执行”。

## 决定

### 1. Run 增加执行器类型与会话归属

`agent_runs` 新增 `executor_kind`（`workflow` / `agent`）与 `session_id`。现有 Worker 只领取 `workflow`，Scheduler 只领取 `agent`；两类 Run 共用事件、取消、审批与 SSE，不再复制一套运行表。

`uq_running_run_user` 的唯一索引改为只约束 `workflow`：同一用户仍不能并发跑两个工作流，但可以有多个会话各自的 agent Run。

### 2. ACK、settled、committed 三阶段分离

| 阶段 | 事件 | 含义 |
| --- | --- | --- |
| ACK | `run.acknowledged` | CLI 接受了 `run.start`，开始执行；**不是成功** |
| settled | `run.settled` | CLI 完成本轮，带 stop_reason、消息与引用；仍不是最终事实 |
| committed | `run.committed` + 终态 | 业务库校验并写入助手消息后才置 `succeeded` |

事件 `seq` 与事件行在同一事务内分配，且分配语句带 fencing token 条件；旧执行者无法把事件写进新 attempt。SSE 的终态判断仍看数据库状态，不会因为收到 settled 就提前结束。

### 3. 每会话一个 CLI 进程，生产实现用 Python

生产 Runner 是 `python -m app.runtime.agent.cli --warm`，每个活跃会话一个进程，stdio 上仍使用冻结的 Runtime JSONL v1 帧（`runtime.bind`、`run.start`、`run.cancel`、`runtime.ping`、`runtime.shutdown`）。

选择 Python 而不是把 M0 的 TypeScript 原型直接产品化，理由：

- 安装包只带一个 Python 运行时，不再引入 Node sidecar 与第二套依赖树；
- 模型网关、工具网关、审计都在后端包内，CLI 只持短期 capability，不持 provider 凭证；
- M0 的 TS 实现继续作为协议一致性参考，帧格式由 `runtime-jsonl-v1.methods.json` 冻结，两边不得各自发明字段。

这不是引入 Agent SDK：循环、状态机、工具调度、结算全部是本仓库代码。

### 4. 每轮一个短期 capability

Scheduler 在绑定会话时签发 HMAC capability，绑定 `user_id/session_id/run_id/attempt/runtime_generation/exp`。CLI 用 `X-Agent-Capability` 调用两个内部端点：

- `POST /internal/agent/model/complete`：SSE 流式返回 delta、tool_call、done；
- `POST /internal/agent/tools/invoke`：只读工具。

capability 每次请求都会核对 Run 仍在运行且 attempt 一致；Run 终态或换 attempt 后旧凭证立即失效。内部端点不进入公开 OpenAPI，也不接受模型传入的 `user_id`。

### 5. 只读职业工具与模型网关

M3 只注册 `search_evidence` 与 `get_profile`，`side_effect=read`；身份只来自 capability，模型参数里出现 `user_id/workspace_id/session_id` 直接拒绝。工具调用写 `audit_events`。

模型网关持有 provider 选择：`demo` 为确定性两轮（先检索、再带证据引用作答），`scripted` 用于故障注入；provider 不可用返回 503，CLI 以 `stop_reason=failed` 结算，不会挂住。

### 6. 审批持久化

`agent_approvals` 记录 invocation、工具、参数摘要与决定。审批时 Run 进入 `waiting_confirmation` 并释放租约；批准后重新入队，新 attempt 不改变 invocation 与 digest；拒绝直接 `cancelled` + `error_code=rejected`。M3 未开放写工具，因此 CLI 不会主动触发审批；审批路径由 API 与存储层测试覆盖。

## 证据

- 新增 39 项测试（`tests/test_agent_*.py`），后端全量 **344 passed / 3 skipped**，覆盖率 **79.52%**（阈值 78%）。
- 真实 CLI 进程 + 桩网关：warm 握手、bind、ACK、流式 delta、工具调用、带引用 settled、gateway 503 时明确 failed。
- API：会话创建、幂等提交、历史游标、`after_seq` 重放、capability 缺失/篡改/错 attempt 分别 401/401/409、工具身份注入被拒、审批拒绝取消、runtime 状态与能力端点。
- Worker 隔离：同样的队列里放入 agent Run，`claim_next` 返回 `None`。
- 旧任务不重复执行：同 Idempotency-Key 返回同一 Run 且不重复写用户消息；运行中的 Run 不会被二次领取。

## 未做与边界

- 真实 provider 闭环（DeepSeek 等）尚未接入 agent 网关；当前只有 demo/scripted。
- 未做 provider token 级流式；demo 的 delta 是网关分片，协议与 UI 投影已按流式处理。
- 写工具、审批恢复后的 digest 消费与工具幂等账本属于 M5。
- 前端会话 UI、Tauri Host 的会话投影属于 M6；当前只有 API 与 CLI。
- CLI 尚未在 AppContainer 中启动；M3 只读工具的威胁面仍按“本机可信进程 + 只读”处理。
