# ADR 0003：Runtime JSONL v1 自定义协议

- 状态：Proposed（待 M0 原型验证）
- 日期：2026-11-27
- 阶段：M0、M3、M4
- 相关规范：V4 §5.1、§5.4、§9.1、§9.3、§18
- 相关契约：[`runtime-jsonl-v1.schema.json`](../../contracts/runtime-jsonl-v1.schema.json)、[`runtime-jsonl-v1.examples.jsonl`](../../contracts/runtime-jsonl-v1.examples.jsonl)
- 参考测试：T09、T10、T27、T28、T32

## 背景

Scheduler 与每个会话 CLI 之间需要双向请求、事件推送和取消。WorkBuddy ACP 与 Pi RPC 可作为职责边界的学习资料，但 V4 明确要求自研 Agent Core、独立实现 Harness，不兼容 ACP，不复用 Pi 的方法名、事件名、会话格式或类型。

## 决定

### 传输与帧边界

- 通道：Scheduler ↔ CLI 的 stdio 双向 JSONL RPC。
- 帧：一行一条严格 UTF-8 JSON，LF 分帧；必须处理半行、CRLF、非法记录和超限帧。
- stdout 只写协议帧；stderr 只写日志；日志不得混入协议。
- `type` 为 `request`、`response` 或 `event`；双向请求通过 `id` 关联，CLI 发起的请求与 Scheduler 发起的请求不得复用同一 ID 空间。
- `v` 固定为 `1`。任何不兼容变化必须升版本并提供显式拒绝或迁移路径。
- 消息大小、并发请求上限、超时、心跳与背压参数只由 M0/M3 实测后写入实现配置，不在本 ADR 编造固定值。

### 三类 envelope

- request：`id`、`method`、`params`。初始方法注册表至少包括 `runtime.bind`、`run.start`、`gateway.invoke`；方法语义在 M3 实现前补入契约。
- response：`id`、`ok`，成功带 `result`，失败带 `error`。请求 ACK 不等于执行完成；`result.accepted` 只表示开始接收。
- event：`run_id`、`attempt`、`runtime_generation`、`local_seq`、`kind`、`payload`。事件用于 UI 投影和诊断，不是业务提交确认。

### 结算语义

V4 自定义三阶段，不复用 Pi 或 ACP 的完成语义：

1. `accepted`：CLI 已验证 Run、代际和输入引用，可开始执行。
2. `settled`：Core 给出候选结果或明确停止原因。
3. `committed`：API 在业务库事务中提交终态、最终消息、产物和 terminal event；只有这一步是 UI 最终成功。

事件必须先注册再发送。`local_seq` 只用于本 CLI 的帧顺序与去重；业务 UI 的持久游标仍使用数据库分配的 Run `seq`，两者不能混用。

## 替代方案与取舍

- **使用 ACP / Pi RPC**：减少协议设计量，但与“不兼容 ACP、不依赖 Pi、不复用上游事件与会话类型”的决定冲突。
- **直接复用现有 Run SSE 作为 CLI 控制协议**：SSE 是单向投影，无法承载双向 gateway 请求、背压和子进程握手。
- **以 JSONL 日志作为权威会话存储**：实现简单，但业务库已有事务、鉴权、删除与事件游标；日志只能是可重建派生状态。

## 风险与待验证项

- 双向 reader/writer 若共用单线程等待，可能在长模型流中无法处理取消；M0 原型必须验证读写并发、取消优先和背压（T32）。
- 工具 intent 提交后，模型流中断不能重新请求该轮；ScriptedModel 必须覆盖截断 JSON、重复 delta、非法参数与取消（T28）。
- 旧 `attempt` 或 `runtime_generation` 的事件必须被拒绝，但已提交的历史事件仍可回放（T09）。
- 方法注册表、错误码、能力协商、心跳格式和最大帧尺寸尚未定稿；这些属于 M3 的具体 PR，不得在实现中临时私有化。
- 本协议不提供 OS 隔离；工具实际执行仍必须经过 Tool Gateway 与沙箱（T16）。

## 验证与回滚

- M0：用 ScriptedModel 完成 `runtime.bind` → `run.start` → `gateway.invoke` → event → settled 的最小链路，并用 `contracts/runtime-jsonl-v1.schema.json` 校验样例。
- M3：验证 ACK/settled/committed 分离、断行、巨帧、stdout 污染、旧代事件和重复 ID。
- 回滚：协议不兼容变化升 `v` 并保留旧版解析入口；不得静默改变字段名或 `type` 含义。若 M0 证明 stdout stdio 方案无法满足并发与背压，先提新 ADR 再改通道。
