# CareerLens Agent Core — M0 原型

这是 V4 §16.1 / §18.3 的 **M0-04 技术门禁原型**：用 ScriptedModel 和内存端口验证自研 Agent Core 的模型→工具→回灌主循环、审批屏障、取消、安全断点恢复和 Runtime JSONL v1 双向 RPC。

**它不是生产运行时**：没有真实模型、真实业务库、真实文件/网络权限、OS 沙箱、持久化事件游标或 HTTP 鉴权。不要把它接入用户数据，也不要把脚本化结果说成模型推理结果。

## 运行

需要 Node 22（本机 22.22.2 已验证）。TypeScript 使用 Node 内置类型剥离，无需安装依赖：

```bash
cd agent-runtime
node --test tests/*.test.ts   # 14 项：引擎 8 + 协议 5 + CLI 1
node src/cli.ts               # stdio JSONL 入口，等待 scheduler 帧
```

CLI 只向 stdout 写 JSONL 协议帧；诊断写 stderr。Scheduler → CLI 请求使用 `s-<n>` ID，CLI → Scheduler 请求使用 `c-<n>` ID。

## 已验证的行为

| 行为 | 测试 |
| --- | --- |
| 零工具正常结束；工具参数分片、重复 delta 幂等、结果回灌后再进入模型 | `tests/engine.test.ts` |
| 截断/非法 JSON 不产生工具意图；慢速流取消后不执行工具 | `tests/engine.test.ts`（T28/T32） |
| 三个工具中间需审批：后续工具不越过屏障；批准后只执行剩余项；拒绝生成结构化结果 | `tests/engine.test.ts`（T29） |
| 预算跨轮累计后停止；断点 JSON 往返与旧版本拒绝 | `tests/engine.test.ts`（T36） |
| 半行缓冲、CRLF/巨帧/非法 UTF-8 拒绝；取消请求不与长任务互相阻塞 | `tests/protocol.test.ts`（T32） |
| `gateway.invoke` 双向配对；CLI 子进程 stdout 全是合法帧 | `tests/cli.test.ts` |

## 显式未做

- 不 fork、不 vendor、不依赖 Pi / ACP / 任何其他 Agent SDK；源码中没有模型供应商 SDK。
- 没有 `approval` 的业务库事务、fencing token、工具账本持久化或真实外部副作用。
- 没有 Runtime Manager、预热池、daemon、Tauri Host 或 OS 沙箱。
- 没有 token 精确计数、上下文压缩、Team/Task 多 Agent 和真实模型评测。

结论与后续门禁见 [`docs/adr/0004-m0-scripted-runner-prototype.md`](../docs/adr/0004-m0-scripted-runner-prototype.md)。
