# ADR 0001：V4 目标进程拓扑与唯一所有权

- 状态：Accepted（设计基线，非实现完成声明）
- 日期：2026-11-27
- 阶段：M0–M9
- 相关规范：V4 §0、§2、§3、§4、§18.1
- 参考测试：T02、T04、T05、T06、T08、T09、T10、T16、T27

## 背景

CareerLens 要同时服务 Web 与 Windows Desktop，并支持证据驱动的长期 Agent 会话。现有 Web 栈已有 FastAPI、LangGraph Worker、Run/Step/Event 和 SQL 业务库；Desktop 需要窗口、托盘、原生文件和后台执行，但不能因此产生第二套业务事实或把 Agent 循环塞进 WebView、daemon 或 API 进程。

M0 第一步只固定边界与所有权，不实现具体进程管理、沙箱或运行时池。

## 决定

### 目标拓扑

```text
Web 工作台 ──HTTPS + SSE──> 远端 FastAPI
Desktop WebView ──Tauri IPC──> Tauri Host ──HTTP + SSE──> 本机 FastAPI
                                      └──ACL IPC──> 用户级 daemon
                                                      ├─ API / Workflow Worker
                                                      ├─ Runtime Manager + Scheduler
                                                      └─ 每活跃主会话一个独立 CLI
                                                          └─自研 CareerLens Agent Core
                                                              └─Tool / Model Gateway
```

- daemon 管本机进程监督、生命周期、调度控制、托盘状态和诊断；不生成回答，不直接改职业数据。
- Agent Loop 只运行在独立 CLI runtime 中；每个活跃主会话绑定一个进程，预热壳不带用户状态。
- 业务后端保留 FastAPI + LangGraph + Worker + SQLite/PostgreSQL；结构化任务继续由现有 Worker 执行。
- 远端部署使用同一 Harness 与调度核心，但由服务端独立部署 scheduler，桌面端不控制远端进程。

### 唯一所有权

| 资源 | 权威所有者 | 明确禁止 |
| --- | --- | --- |
| 窗口、文件选择、保存、托盘 | Tauri Host | 渲染层直接启动 shell 或持有长期令牌 |
| 本机 daemon 与受管子进程 | Daemon Supervisor | Host 与 daemon 同时重启同一子进程 |
| 会话 runtime 绑定 | 按部署实例的 Runtime Manager | 同一会话有两个同时有效的 runtime |
| Evidence、身份、Run、消息、审批、产物 | FastAPI 领域服务与数据库 | CLI 直接读写业务库，JSONL 日志成为第二权威 |
| 结构化任务 | 现有 Worker / Run 体系 | Agent 与 Worker 建立两套业务状态 |
| Agent Run 领取 | Scheduler dispatch + AgentService | Worker 与 scheduler 双重领取 |
| 模型凭证 | 本机凭证库 / 服务端 secrets / Model Gateway | 预热进程、网页 JS、日志持有长期密钥 |
| 文件与网络能力 | File / Network / Tool Gateway | 模型提供 `user_id`、任意路径或任意命令后直接执行 |

业务库是 Run、会话、事件、审批和证据的唯一权威；CLI 内存与 JSONL 只是派生状态。外部动作即使已发出但结果不明，也必须标为 `unknown` 并核查，不能靠重发保证一致性。

## 替代方案与取舍

- **Electron**：可更快复用 Web 能力，但增加运行时体积与权限模型差异；V4 先验证 Tauri。仅当静态导出无法满足且拆分共享 UI + Vite 桌面入口仍失败时，才另写 ADR 重选。
- **把 Agent Loop 放进 daemon / WebView / API**：进程少，但会话状态、权限与崩溃边界混杂，无法满足一次绑定、旧代拒写和独立会话恢复。
- **fork/vendor Pi 或引入其他 Agent SDK**：可能减少初期代码量，但与自研 Core 目标冲突；本方案不采用，实际复用第三方代码必须先取得用户同意并核对许可证。
- **照搬 WorkBuddy ACP 与私有结构**：WorkBuddy 的 daemon 角色是本项目自己的设计决定；只保留进程隔离、生命周期、事件重放、一次绑定预热与权限分层等原则。

## 风险与约束

- 静态 Next.js export、WebView origin、上传和 SSE 尚未在 Tauri 中验证；Web standalone build 必须保持可回归。
- Windows Job Object 的嵌套 job、句柄继承和宿主已在 job 中的失败路径尚未验证；不能建立约束时禁用高风险运行时。
- AppContainer 或等效受限 token 与 Node、Python、命名管道和模型流的兼容性尚未验证；Job Object 不能代替文件与网络隔离。
- 每 OS 用户一套 daemon、一份 SQLite 业务库；多个职业工作区是逻辑隔离，不是一个 API/Worker 同时路由多份数据库。

## 落地映射

| 参考资料（仅记文档名称） | 设计原则 | CareerLens 模块 | 测试 ID | 事实边界 |
| --- | --- | --- | --- | --- |
| WorkBuddy 端到端学习走查、CLI 与 Daemon 架构设计 | 宿主协调、daemon 常驻服务、每会话独立 CLI | Tauri Host、daemon、Session CLI | T04、T05 | 参考事实；V4 daemon 管调度是设计决定 |
| 运行时生命周期与预热池、专题 5 | 预热壳无用户状态；绑定一次后销毁 | Runtime Manager、warm pool | T06、T07 | 参考事实 |
| agent_harness 架构讲解 | 以“谁持有状态、谁发问题和收事件”判断所有权 | ADR、Runtime Manager | T08、T09 | 参考事实 |
| 工具权限与沙箱、沙箱与执行环境隔离 | 协议门、工具门、执行环境三层不可合并 | Tool Gateway、File/Network Broker | T14、T15、T16 | 参考事实；CareerLens 实现待验证 |
| V4 §2.1 唯一所有权表 | 业务库唯一权威，审批与工具账本持久化 | Run/Event/Approval Store | T09、T10、T12 | 目标架构决定，尚未实现 |

## 验证与回滚

- 阶段门禁：M0 输出进程拓扑原型和诊断证据；M1 验证同主体 Web/桌面共用 Run ID；M2 验证关闭 UI 后任务继续且完全退出无孤儿；M4 验证一次绑定与旧代拒绝。
- 回滚：若 Tauri 静态导出失败，先拆共享 UI + Vite 桌面入口；若 OS 沙箱无法通过攻击测试，禁用相应高风险工具而不宣称沙箱成立；若进程池设计无法通过 M4，保留 CLI 与业务库边界并提新 ADR 调整池实现。
- 本 ADR 不授权实现持久化 schema、外部命令或新 API；后续 PR 必须逐项引用对应契约与测试。
