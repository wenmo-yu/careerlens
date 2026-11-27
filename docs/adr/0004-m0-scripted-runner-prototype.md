# ADR 0004：M0 自研 Runner 原型与验证边界

- 状态：Accepted（仅作为 M0 原型结论，不是生产运行时验收）
- 日期：2026-11-27
- 阶段：M0、M3
- 相关规范：V4 §5.2、§5.4、§5.5、§9.1、§16.1、§18.3、§18.4
- 相关实现：[`agent-runtime/`](../../agent-runtime/README.md)、[`runtime-jsonl-v1.schema.json`](../../contracts/runtime-jsonl-v1.schema.json)
- 参考测试：T27、T28、T29、T32、T36

## 背景

V4 要求自研 Agent Core，但不能过早接真实业务库、真实模型或 OS 沙箱。M0 需要先用确定性夹具证明：模型响应完整后才提交工具意图；审批可以形成屏障并能恢复；取消不会被长模型流阻塞；stdio 协议不会把日志混入事实通道。

## 决定

1. 新增独立 `agent-runtime/` TypeScript 原型，使用 Node 22 内置类型剥离执行，不引入任何 Agent SDK、Pi 包或 vendored 源码。依赖为零，CI 不需要额外安装步骤。
2. Core 只通过 `EnginePorts` 接口工作：`model`、`tools`、`store`、`budget`、`events`、`approvals`。原型端口全部在内存，不接触 FastAPI、SQLite、凭证或文件。
3. 主循环按 `prepare → model_stream → tool_plan → tool_execute → validate → settled` 推进。只有完整、合法、正常结束的模型响应才能生成工具意图；截断或非法参数直接记为 `model_error`，不执行任何工具。
4. `invocationId = runId:turnId:ordinal`，由可信 Runner 分配；参数摘要使用 SHA-256。审批绑定摘要，一次消费。审批中的工具形成屏障，同轮后续工具不得越过。
5. `approval_required` 是本次执行退出，不是 Run 终态。恢复时从已提交的安全断点进入 `tools`，只执行未配对意图，不重新请求已提交轮次的模型。
6. Runtime JSONL v1 保持自定义双向 RPC：Scheduler 请求用 `s-<n>`，CLI 请求用 `c-<n>`；读循环不等待 handler，取消与 gateway 响应可并发处理；stdout 只写协议帧。
7. 原型明确不提供：真实模型、业务库事务、fencing、预热池、daemon、Tauri、OS 沙箱、上下文压缩、多 Agent 与真实工具副作用。

## 验证证据

命令（工作目录 `agent-runtime/`）：

```bash
node --test tests/*.test.ts
```

2026-11-27 本机 Node 22.22.2 实测：**14/14 通过**（引擎 8、协议 5、CLI 1）。覆盖：

- T27：源码无 Pi / ACP / Agent SDK 依赖；独立 DTO 与端口。
- T28：截断 JSON、`{"query": nope}`、未闭合 JSON 三种坏流均不触发工具；重复相同 delta 只生成一个意图。
- T29：三个工具中间需审批时只执行第一个；批准后恢复只执行剩余两个，模型请求数仍为 2；拒绝时留下结构化 `denied` 结果且不会执行副作用。
- T32：慢流中取消先返回，工具未执行；长 handler 等待期间 `run.cancel` 的响应先于 `run.start` 到达；`gateway.invoke` 通过 `c-` ID 正确配对。
- T36：预算跨轮累计，`maxTurns=1` 在工具回灌后的下一轮以 `budget_exhausted` 停止，计数不重置。
- CLI 子进程 stdout 每行都可按 v1 schema 解码，确认日志未污染协议通道。

## 替代方案与取舍

- **复用 Pi / OpenAI Agents SDK**：会更快得到循环，但违反自研约束，且把上游状态/事件语义带进契约；不采用。
- **只在现有 LangGraph Worker 里加 Agent 节点**：省进程，但无法验证独立 CLI、审批屏障和 JSONL 双向取消；不属于本门禁。
- **先接真实模型**：脚本化夹具能覆盖流中断、重复分片和坏 JSON；真实模型评测放到 M3/M9，避免用网络波动掩盖状态机缺陷。

## 风险、边界与回滚

- 原型的是状态机与协议，不是安全边界。任何真实工具、凭证或用户资料接入前必须通过 M3/M5 的持久化、授权、fencing 与 OS 沙箱门禁。
- `localSeq` 是单次 CLI 的帧序号，不代替数据库分配的持久 `seq`；恢复后从不假定它连续。
- 断点只覆盖明确的 turn 边界；没有序列化网络流、Promise 或进程内存。
- 本机 Rust 工具链已安装（1.100.0），但缺少 MSVC C++ build tools，`link.exe` 不可用，因此 Tauri 原生编译门禁仍未验证。该事实只写本地记录，不把未完成的原型当生产实现。
- 回滚：删除 `agent-runtime/`、本 ADR、CI 对应 job 与导航链接即可；不改变 Web/API、现有 Worker 或任何业务 schema。

## 下一门禁

M0-02（Tauri 静态导出 + 真实登录/上传/SSE）与 M0-03（Python 打包、Windows Job Object / AppContainer）仍未通过；它们需要原生链接器或干净 Windows 环境，不能由本原型的通过代替。
