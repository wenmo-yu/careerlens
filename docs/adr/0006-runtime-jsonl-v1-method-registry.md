# ADR 0006：Runtime JSONL v1 方法注册表与错误码

- 状态：Accepted（v1 方法集与错误码冻结；能力协商与心跳节奏仍待 M3）
- 日期：2026-11-27
- 阶段：M0（收口）、M3（前置契约）
- 相关规范：V4 §5.1、§5.4、§9.1、§9.3
- 相关决策：[0003](0003-runtime-jsonl-protocol-v1.md)、[0004](0004-m0-scripted-runner-prototype.md)
- 相关契约：[`runtime-jsonl-v1.methods.json`](../../contracts/runtime-jsonl-v1.methods.json)、[`runtime-jsonl-v1.schema.json`](../../contracts/runtime-jsonl-v1.schema.json)
- 参考测试：T09、T27、T32

## 背景

ADR 0003 只固定了帧形状，方法注册表、错误码与心跳被显式留到 M3。M0-04 原型里方法名、错误码是散落在 `runtime-host.ts` 里的字符串分支：未知方法会落到 `handler_error`，缺参会直接在处理器里读到 `undefined`，重复请求 id 会执行两次。这类问题在真实模型与真实工具接进来之后才会变成难以定位的故障，因此必须在实现调用方之前把契约固化成机器可读文件。

## 决定

### 1. 方法集与方向

v1 冻结以下五个方法，超出集合的方法名一律按 `unknown_method` 拒绝，不做兜底执行：

| 方法 | 方向 | id 空间 | 必填参数 | 幂等 |
| --- | --- | --- | --- | --- |
| `runtime.bind` | 调度器 → CLI | `s-<n>` | `session_id` | 是 |
| `runtime.ping` | 调度器 → CLI | `s-<n>` | 无 | 是 |
| `run.start` | 调度器 → CLI | `s-<n>` | `run_id` | 否 |
| `run.cancel` | 调度器 → CLI | `s-<n>` | 无 | 是 |
| `gateway.invoke` | CLI → 调度器 | `c-<n>` | `tool` | 否 |

`run.cancel` 在 M0-04 已存在于实现但未进契约，本轮补入；`runtime.ping` 是新增的最小存活探测，返回 `{pong, ping_seq, bound}`，不触发任何副作用，也不代表 Run 还活着。

### 2. 错误码与语义

错误码写在契约的 `error_codes` 中，每个码带 `emits_response` 与 `retryable` 两个布尔位，实现按位执行：

- 帧级失败（`invalid_frame`、`invalid_json`、`frame_too_large`、`unknown_type`）不产生响应、不产生副作用，整行丢弃。
- 请求级失败会产生响应：`invalid_id_space`、`unknown_method`、`invalid_params`（带 `details.missing`）、`duplicate_request`、`run_busy`、`handler_error`。
- `runtime_closed` 表示 stdin 关闭时仍有未返回的 CLI 请求，不可假定成功。
- `run_busy` 是唯一默认可重试的请求级错误：同一 CLI 在已有活动 Run 时再次 `run.start` 会被拒，调度器应等结算或先 cancel。

### 3. 校验顺序

实现按固定顺序判定，避免"未知方法被当成参数错误"这类误报：

1. id 空间 → `invalid_id_space`
2. 重复 id → `duplicate_request`
3. 方法是否存在 → `unknown_method`
4. 必填参数 → `invalid_params`
5. 活动 Run 冲突 → `run_busy`
6. 执行处理器 → 成功或 `handler_error`

重复 id 在进入处理器之前就被拒绝，因此不会产生第二次副作用；追踪表有上限（默认 512 条，先进先出），长会话不会无界增长。

### 4. 落地位置

- 契约：`contracts/runtime-jsonl-v1.methods.json`（唯一对外发布版本）。
- 执行点：`agent-runtime/src/protocol/methods.ts`，`runtime-host.ts` 只调用注册表。
- 测试：`agent-runtime/tests/methods.test.ts`，5 项覆盖未知方法、缺参、重复 id、ping 的绑定状态、`run_busy` 与取消后可重入。

## 替代方案与取舍

- **把方法集留在实现里，不单独出文件**：调用方要读 TypeScript 才能知道参数，跨语言调度器（Python 侧）会各写一份，最终产生第二权威。拒绝。
- **未知方法回退到 `handler_error`**：M0 原型就是这么做的，导致"版本不匹配"与"处理器内部报错"无法区分。改为 `unknown_method` 后可直接定位。
- **用 ACP 的方法名对齐**：与"不兼容 ACP、不复用上游方法名"的决定冲突，且会把上游语义带进来。
- **现在就做能力协商（capability negotiation）**：缺少真实模型与多版本客户端的失败用例，先留空，等 M3 有真实调用方再定。

## 风险与待验证项

- `ping_seq` 是 CLI 本地计数，不是业务心跳；崩溃检测仍需调度器侧超时策略，本 ADR 不规定心跳间隔。
- 方法集冻结不等于能力冻结：工具白名单、审批策略、子代理方法仍可能在 M3 增加新方法，新增必须升 `v` 或走可选方法协商。
- 契约 JSON 与 `methods.ts` 是两份手写副本，存在漂移风险；后续应在 CI 增加一致性检查（读 JSON 断言与 TS 导出集合相同）。
- 未验证：真实模型流下的 `run_busy` 竞态、跨进程重连后的重复 id 复用、超长会话下追踪表淘汰后的重复请求。

## 验证与回滚

- 本机 `node --test tests/*.test.ts`：20 项全部通过（含 6 项新增 M3 契约测试，其中 1 项校验契约 JSON 与运行时注册表一致）。
- 回滚：删除 `contracts/runtime-jsonl-v1.methods.json`、`methods.ts`、`methods.test.ts`，`runtime-host.ts` 恢复为 M0-04 的分支实现即可；因为方法集只增不减，回滚不会破坏已发布帧格式。
