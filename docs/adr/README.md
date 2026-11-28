# 架构决策记录（ADR）

本目录记录 CareerLens Desktop V4 中不可在编码阶段随意改动的架构决定。每条 ADR 写明选择、替代方案、风险、回滚方式和验证证据。状态为 `Accepted` 只表示设计基线已纳入仓库，不表示该能力已经实现。

| 编号 | 决策 | 状态 | 对应阶段 |
| --- | --- | --- | --- |
| [0001](0001-v4-process-topology-and-ownership.md) | 目标进程拓扑与唯一所有权 | Accepted（设计基线） | M0–M9 |
| [0002](0002-api-compatibility-baseline.md) | API 兼容基线 | Accepted（当前 API 快照） | M0–M3 |
| [0003](0003-runtime-jsonl-protocol-v1.md) | Runtime JSONL v1 自定义协议 | Accepted（帧格式与方法集已冻结，实装见 0010） | M0、M3、M4 |
| [0004](0004-m0-scripted-runner-prototype.md) | M0 自研 Runner 原型与验证边界 | Accepted（仅原型结论） | M0、M3 |
| [0005](0005-m0-static-export-packaging-and-job-object.md) | M0 静态导出、Python 打包与 Job Object 边界 | Accepted（仅原型证据） | M0 |
| [0006](0006-runtime-jsonl-v1-method-registry.md) | Runtime JSONL v1 方法注册表与错误码 | Accepted（v1 方法集冻结） | M0、M3 |
| [0007](0007-m1-daemon-supervision-prototype.md) | M1 用户级 Daemon 原型与进程监督边界 | Accepted（原型证据；实装见 0009） | M1、M2 |
| [0008](0008-daemon-control-protocol-v1.md) | Daemon 控制协议 v1（管道、握手、命令与错误码） | Accepted（v1 命令集冻结） | M2 |
| [0009](0009-daemon-implementation-step-one.md) | Daemon 实装第一步：模块边界与可测性 | Accepted（已进入 `backend/`） | M2 |
| [0010](0010-m3-agent-runtime-contract.md) | M3 持久 Agent 运行契约、capability 与只读工具 | Accepted（只读闭环；真实模型/写工具未开放） | M3 |
| [0011](0011-m4-runtime-manager.md) | M4 预热池、租约、代际与准入 | Accepted（池与调度原型进入 `backend/`） | M4 |
| [0012](0012-m5-model-gateway-provider.md) | M5 OpenAI-compatible 流式模型网关 | Accepted（接口冻结；真实供应商端到端未验证） | M5 |
| [0013](0013-m5-tool-ledger-and-approval.md) | M5 工具账本与写工具审批/恢复闭环 | Accepted（数据库写入；OS 沙箱未做） | M5 |
| [0014](0014-tauri-host-and-daemon-control.md) | Tauri 2 桌面宿主与 Daemon 控制面骨架 | Accepted（骨架实现；安装包签名与升级未验证） | M2、M6 |
| [0015](0015-m6-multi-agent-task-tree.md) | M6 多任务树、角色隔离与结果投影 | Accepted（持久契约与 API；真实质量评测未做） | M6 |
| [0016](0016-m8-durable-schedules.md) | M8 持久计划与去重触发 | Accepted（内部触发；系统唤醒未做） | M8 |
| [0017](0017-m5-workspace-file-broker.md) | M5 工作区文件 broker 与路径授权 | Accepted（应用层边界；不是完整 OS 沙箱） | M5 |
| [0018](0018-runtime-heartbeat-health.md) | Worker 与 Scheduler 显式心跳健康语义 | Accepted（runtime/status 已实现；ready 语义不变） | M2、M9 |
| [0019](0019-agent-workbench-ui.md) | Agent 工作台最小界面 | Accepted（静态导出通过；真实桌面体验未验证） | M6 |
| [0020](0020-m8-role-lifecycle.md) | M8 持久角色生命周期与工具收窄 | Accepted（持久契约与服务端收窄；长期运行未验收） | M8 |
| [0021](0021-m8-inbox-and-search.md) | M8 应用内通知与任务搜索 | Accepted（派生通知与只读搜索；系统唤醒/投递未做） | M8 |
| [0022](0022-m8-mcp-connector-admission.md) | M8 MCP 受控接入准入策略层 | Accepted（准入策略已实现；隔离执行与网络策略需 OS 沙箱） | M8 |

## 优先级

1. V4 规范中的明确决定；
2. 当前仓库的实际契约与测试；两者冲突时先提新 ADR，不能私下改范围；
3. 学习资料中的架构原则；
4. 上游实现细节。

公开文档只记录设计名称和公开链接。本机技术资料的绝对路径、反编译产物及私人研究正文不进入公开仓库。
