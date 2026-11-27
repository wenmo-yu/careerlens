# ADR 0008：Daemon 控制协议 v1

- 状态：Accepted（v1 命令集与错误码冻结；原型已按此实现）
- 日期：2026-11-27
- 阶段：M2-01（Daemon 协议与实例锁）
- 相关规范：V4 §9（运行环境）、§18.1、T04、T05
- 相关决策：[0001](0001-v4-process-topology-and-ownership.md)、[0007](0007-m1-daemon-supervision-prototype.md)
- 相关契约：[`daemon-control-v1.json`](../../contracts/daemon-control-v1.json)

## 背景

ADR 0007 的 daemon 原型已经能监督 API 与 Worker、回收进程组，但控制面是临时拼的：命令名、返回字段、错误表达都没有契约，`status` 返回的形状随时会变。M2-01 要交付的是"daemon 协议与实例锁"，如果先写实现再补文档，Host、托盘和未来的 CLI 各自会按自己的理解接一遍。

因此本轮先把控制协议固化为机器可读契约，并让原型按契约实现、用测试验证，而不是只写一份描述。

## 决定

### 传输与安全

- 传输：Windows 命名管道 `\\.\pipe\careerlens-daemon-<instance>`，UTF-8 JSON 行协议，单条上限 64 KiB。
- 不新增 HTTP 回环端口：HTTP 对任何本机进程开放，DACL 只能靠令牌；管道可以直接按 SID 限定。
- DACL 固定为 `D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;<当前用户 SID>)`：只有 SYSTEM、Administrators 与创建 daemon 的用户可访问。客户端不带令牌，身份由管道 ACL 与进程所有者共同决定。

### 握手

任何连接必须先 `hello`：

- 客户端带 `protocol`（v1 为 `1`）与 `client` 标识。
- daemon 返回 `protocol`、`daemon_version`、`pid`、`instance_id`、`started_at`、`roles`。
- 版本不支持时返回 `protocol_mismatch` 与 `supported: [1]`，客户端应升级而不是重试。
- 未握手的连接发其它命令只会收到 `not_ready`。

### 命令集

| 命令 | 必填参数 | 结果必填 | 幂等 |
| --- | --- | --- | --- |
| `hello` | `protocol`、`client` | `protocol`、`daemon_version`、`pid`、`instance_id`、`roles` | 是 |
| `ping` | 无 | `pong` | 是 |
| `status` | 无 | `daemon`、`backend`、`children` | 是 |
| `restart` | `role`（仅 `api`/`worker`） | `restarting` | 否 |
| `stop` | 无 | `stopping` | 是 |

错误码：`unknown_command`、`invalid_params`、`unknown_role`、`protocol_mismatch`、`not_ready`（可重试）、`internal_error`（可重试）。

### 边界

- `status` 只反映进程与健康，不持有 Run、会话、审批或证据；业务事实仍在 FastAPI 与业务库。
- `stop` 只结束 daemon 与受管子进程，不删数据库、不改 Run 终态。
- 控制面与日志都不得出现用户内容、令牌或提示词。

## 原型验证

在 ADR 0007 的 daemon 原型上按契约实现，端到端检查 14 项全部通过：

| 检查 | 结果 |
| --- | --- |
| `hello 1` 返回 `protocol=1` 与 `instance_id` | ok |
| `hello 2` 返回 `protocol_mismatch` 且 `supported=[1]` | ok |
| 未握手直接 `status` 返回 `not_ready` | ok |
| 未知命令返回 `unknown_command` | ok |
| 单实例锁、双进程存活、后端健康 | ok |
| `taskkill` 后 API 重启、`restarts=1`、恢复健康 | ok |
| `stop` 退出码 0、无孤儿 | ok |
| 强杀 daemon 后 Job Object 回收子进程 | ok |

实现期间发现一处语义要修正：已握手的连接再发一个不支持的 `hello` 时，不应把已有握手状态清掉，否则后续命令会意外变成 `not_ready`。契约里的握手规则已按"不降级"实现。

## 替代方案与取舍

- **控制面走 HTTP + Bearer**：实现最快，但任何本机进程都能连，且需要另建一套令牌体系；与"受 ACL 保护的本地 IPC"冲突。
- **复用 Runtime JSONL v1**：两者方向、语义、生命周期都不同（Runtime 面向 Agent 会话，Daemon 面向进程监督），复用会让两套契约互相污染。
- **不做契约、直接靠实现**：Host、托盘、诊断工具会各自猜字段，最终产生第二权威。

## 风险与待验证

- 原型一次只持有一个管道实例，并发客户端会拿到 `ERROR_PIPE_BUSY`；客户端目前靠重试解决，M2 需要改成多实例或 overlapped I/O。
- `status` 的健康判据仍是业务 HTTP 200，未区分"API 活着但 Worker 死了"。
- 未验证：非本机用户连接被 DACL 拒绝、管道被恶意客户端占满、daemon 版本升级时的协议共存。
- 契约与实现是两份手写副本，M2 应像 Runtime 契约那样加一致性测试。

## 回滚

删除 `contracts/daemon-control-v1.json`、本 ADR 与索引条目即可；原型在仓库外，撤销不影响 `careerlens/` 的构建与 CI。
