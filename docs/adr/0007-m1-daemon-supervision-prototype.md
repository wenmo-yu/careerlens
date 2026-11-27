# ADR 0007：M1 用户级 Daemon 原型与进程监督边界

- 状态：Accepted（原型证据；实装见 [0009](0009-daemon-implementation-step-one.md)）
- 日期：2026-11-27
- 阶段：M1（前置验证）、M2（设计输入）
- 相关规范：V4 §2（进程拓扑）、§9（运行环境）、§18.1、T04、T05
- 相关决策：[0001](0001-v4-process-topology-and-ownership.md)、[0004](0004-m0-scripted-runner-prototype.md)、[0005](0005-m0-static-export-packaging-and-job-object.md)
- 参考测试：T04、T05、T16

## 背景

M0 已经分别验证了打包后端、自研 Runner 和 Job Object 单项能力，但三者没有被同一个常驻进程串起来：关掉 UI 后谁还在跑、API 崩了谁重启、daemon 死了子进程会不会变成孤儿，这些是 M2 的验收核心（T04/T05），也是"网页套壳"和"桌面产品"的分界线。ADR 0001 已把职责定死：daemon 只管进程监督与调度，不生成回答、不跑 Agent Loop、不直连业务库。

本轮做的是一个 Windows 用户级 daemon 原型，用来提前验证这套拓扑能不能真的落地，而不是先写 M2 代码再补证据。

## 决定与证据

### 原型承担的四件事

1. **单实例**：命名互斥量 `Global\CareerLens.Daemon.*`，第二个实例以退出码 3 结束并打印 `DAEMON_ALREADY_RUNNING`。
2. **进程组回收**：`CreateJobObjectW` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`，daemon 自己也被加入该 job，因此 daemon 异常消失时内核会关闭 job 句柄并回收全部受管子进程（T05 的进程侧）。
3. **监督**：从同一个打包 exe 以不同环境变量拉起 API（`CAREERLENS_PROBE_SERVE=1`）与 Worker（`CAREERLENS_PROBE_WORKER=1`），每 0.4 s 轮询子进程状态，HTTP `GET /health/live` 作为后端健康判据；异常退出按 `0.5 × 2^(n-1)`（上限 15 s）退避重启，一分钟内超过 6 次则熔断并记录 `child.circuit_open`。
4. **控制面**：命名管道 `\\.\pipe\careerlens-daemon-*`，用 SDDL `D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;<当前用户 SID>)` 设置 DACL，只允许本机 SYSTEM、Administrators 和当前用户；命令为 `status` / `restart <role>` / `stop`，返回 JSON。

### 实测结果（本机 Windows，打包产物 + SQLite）

| 检查 | 结果 |
| --- | --- |
| daemon 启动并就绪 | ok（`daemon.ready healthy=true`） |
| API 与 Worker 同时运行 | ok |
| `/health/live` 200 | ok |
| 第二个实例被实例锁拦住 | ok（退出码 3，`DAEMON_ALREADY_RUNNING`） |
| `taskkill /F` 杀掉 API 后自动重启 | ok（新 PID，`restarts=1`） |
| 重启后后端恢复健康 | ok |
| `stop` 优雅退出 | ok（退出码 0） |
| 退出后无孤儿进程 | ok（两个 PID 都不再存活） |
| 强杀 daemon 后 Job Object 回收子进程 | ok（两个 PID 在 30 s 内消失） |

### 原型期间踩到的两个 Windows 细节

- **句柄不能靠默认返回值传**：`CreateJobObjectW` / `CreateNamedPipeW` 若不声明 `restype`，64 位下 HANDLE 会被截断成 32 位，后续 `AssignProcessToJobObject` 直接 `ERROR_INVALID_HANDLE`。
- **关闭仍在 `ConnectNamedPipe` 的管道句柄会阻塞**：daemon 收到 `stop` 后日志已经打印 `daemon.stopped`，进程却退不掉。原因是有线程阻塞在 `ConnectNamedPipe`，`CloseHandle` 会等这次 pending 同步 I/O。修法是先用一次客户端连接把控制线程唤醒、`join` 后再关闭句柄。
- **daemon 自己在 job 内**：优雅退出时不应再显式 `CloseHandle(job)`，否则 `KILL_ON_JOB_CLOSE` 会把 daemon 自己杀掉，掩盖优雅退出路径。此时子进程已先停止，句柄交给进程退出时由内核回收。

## 显式未做

- 没有托盘、开机启动、关闭窗口后台运行的 UI 联动；daemon 目前只能命令行启动。
- 没有代码签名、固定安装路径、自动更新；原型直接跑缓存目录里的 exe。
- 没有 CLI 预热池、并发配额（V4 规定主会话 4、CLI 总 6）、会话锁；只监督 API 与 Worker 两种角色。
- 没有 SQLite 迁移/备份、多工作区隔离、日志滚动与脱敏诊断包。
- 控制协议还没有版本化握手；M2 必须像 Runtime JSONL 一样先定契约再加实现。
- 健康判据复用业务 HTTP 端点，不是 daemon 自有的存活探测；API 卡死但端口仍在时会被误判为健康。

## 替代方案与取舍

- **把 API 与 Worker 塞进 daemon 进程内**：省掉 IPC，但会让 daemon 直接持有业务状态，违反"daemon 不直连业务库、不生成回答"的边界，也让崩溃恢复失去隔离。拒绝。
- **用 Windows 服务（系统级）**：能开机自启，但需要管理员权限，与"用户级、不装默认高权限服务"的决定冲突。
- **用 `multiprocessing`/`subprocess` 的 `terminate` 兜底而不做 Job Object**：daemon 被强杀时子进程会残留，T05 直接不通过。
- **控制面走 HTTP 回环端口**：实现简单，但任何本机进程都能访问，DACL 只能靠令牌；命名管道可以按 SID 限定，更贴近 V4 的"受 ACL 保护的本地 IPC"。

## 风险与回滚

- 原型把 daemon 自己放进 job，若未来需要 daemon 在 job 外继续存活（例如让 UI 触发重启），必须重新设计 job 归属与句柄持有者。
- 退避与熔断参数是经验值，没有在慢机器或磁盘故障下压测；M2 需要用故障注入验证。
- 控制管道使用阻塞 I/O + 唤醒连接，属于原型手段；M2 应改为 overlapped I/O 或消息循环，避免关闭阶段的时序依赖。
- 健康判据只看 HTTP 200，没有区分"API 活着但 worker 死了"；M2 需要把 worker 心跳纳入统一状态。
- 回滚：本 ADR 只记录证据，`careerlens/` 仓库没有引入 daemon 源码；撤销只需删除本 ADR 与索引条目。

## 下一步（M2 输入）

1. 先定 daemon 控制协议（版本、握手、命令集、错误码），再写实现；不要先有管道再有契约。
2. 把 API/Worker/CLI 三类进程的配额、健康与重启策略写成配置，而不是散落在监督循环里。
3. 补托盘与"关闭窗口是否继续"的用户选择，并把真实状态回显到 UI（V4 要求显示 PID、版本、队列与失败）。
