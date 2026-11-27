# ADR 0009：Daemon 实装第一步（模块边界与可测性）

- 状态：Accepted（实现已进入 `backend/`；托盘、开机启动、迁移仍未做）
- 日期：2026-11-27
- 阶段：M2
- 相关规范：V4 §9、§18.1、T04、T05
- 相关决策：[0001](0001-v4-process-topology-and-ownership.md)、[0007](0007-m1-daemon-supervision-prototype.md)、[0008](0008-daemon-control-protocol-v1.md)
- 相关契约：[`daemon-control-v1.json`](../../contracts/daemon-control-v1.json)

## 背景

ADR 0007 的 daemon 原型证明了拓扑可行，但代码在仓库外，不能进 CI、不能被 Host 依赖、也没有和 ADR 0008 的契约绑定。M2 的第一步不是加功能，而是把原型搬进产品代码，并保证它在 Linux CI 上也能被测试，而不是只能在一台 Windows 机器上手工跑。

## 决定

### 1. 位置与包结构

按 V4 目录约定放在 `backend/app/runtime/daemon/`，与既有 `worker.py`、`operations.py`、`parse_input.py` 同级，入口为 `python -m app.runtime.daemon --api-exe <path>`：

| 模块 | 职责 | 平台 |
| --- | --- | --- |
| `contract.py` | 读取 `contracts/daemon-control-v1.json`，缺失时回退到内置副本 | 全平台 |
| `supervisor.py` | 角色、子进程状态、退避重启、熔断、状态快照（纯逻辑） | 全平台 |
| `control_ipc.py` | 契约驱动的命令分发（纯逻辑）+ Windows 命名管道服务端 | 分发全平台，管道仅 Windows |
| `lifecycle.py` | 单实例、进程树归属、健康探测、运行循环 | 锁/进程组全平台，Job Object 仅 Windows |

关键约束：**模块导入不得依赖 Windows**。所有 `ctypes` 都在函数内导入，`sys.platform` 分支只影响运行路径，因此 Linux 上 `import app.runtime.daemon` 与纯逻辑测试都能跑。

### 2. 依赖注入而不是全局状态

`Supervisor` 的 `spawn`、`health`、`now`、`sleep` 全部由调用方注入，`ControlPlane` 只依赖 `Supervisor` 与一个 `ready()` 回调。结果是退避序列、熔断窗口、命令分发都能用假进程和假时钟在毫秒级测试，不需要真的启动 135 MB 的打包 exe。

### 3. 契约在运行时加载，但有内置副本

打包后的 daemon 旁边没有仓库 checkout，读到 `contracts/` 的概率为零。因此 `contract.py` 内置一份与契约文件同构的副本：文件存在时用文件，缺失时用内置，`tests/test_daemon_contract.py` 断言两者命令集、必填参数、错误码完全一致。这与 `agent-runtime` 的做法一致，避免"文档一份、实现一份"。

### 4. 只做四件事

本轮实装范围严格限定为：单实例锁、按契约的控制面、API/Worker 监督与重启、进程树回收。托盘、开机启动、关闭窗口后台、SQLite 迁移/备份、CLI 配额与预热池都不做——它们是 M2 后续 PR，不能混在"迁移"里悄悄扩大。

## 验证

- 跨平台单元测试 41 项（`tests/test_daemon_contract.py`、`test_daemon_supervisor.py`、`test_daemon_control.py`、`test_daemon_lifecycle.py`）：契约与内置副本一致、版本不匹配拒绝、退避与上限、熔断开合、窗口过期、单角色重启、停止语义、握手/未握手/未知命令/未知角色/未就绪、单实例锁、spawner 环境、健康探测与就绪等待。
- Windows 专属测试 4 项（`tests/test_daemon_windows.py`）：互斥量独占与释放、Job Object 自加入、管道 DACL 建立后的命令分发、同一连接内 hello→status 的真实往返。CI 新增 `daemon-windows` job（windows-latest）专门跑这一组，避免平台专属代码只在某台机器上手工验过。
- `ruff check` 通过（E/F/I/UP/B，line-length 100）。
- 后端全量测试 300 passed、覆盖率 78.65%（CI 阈值 78%）；`ruff` 通过。
- 真实集成（本机，Windows）：用 `python -m app.runtime.daemon` 监督打包 exe，`status` 返回 `version=0.2.0-m2` 与两个子进程；`taskkill` 掉 API 后自动重启并 `restarts=1`；第二个实例退出码 3；经该 daemon 跑完整业务链路（注册→证据→画像→chat→Run SSE 16 事件→`succeeded`）；`stop` 后 daemon 与两个子进程全部退出，无孤儿。

## 替代方案与取舍

- **把 daemon 做成独立顶层目录（如 `desktop/daemon/`）**：打包时要么多一个产物，要么重复依赖管理；V4 目录树已把 daemon 放在 `backend/app/runtime/daemon/`，跟随即可。
- **用 Rust 写 daemon**：Job Object 与管道更顺手，但会引入第二套构建与依赖链，而当前阶段要的是"能被 pytest 覆盖的监督逻辑"。等 M2 后期如果 IPC 性能成为瓶颈再评估。
- **直接让 Host 进程兼任 supervisor**：关闭窗口后任务就断了，违反 T04。
- **用 HTTP 控制面**：与 ADR 0008 的 DACL 决定冲突。

## 风险与待验证

- 管道仍是单实例阻塞模型，并发客户端会 `ERROR_PIPE_BUSY`；生产需要多实例或 overlapped I/O。
- `stop` 命令走的是"置位 + 唤醒管道 + join"，属于原型手法；高并发下的关闭时序未压测。
- 健康判据只有 API 的 `/health/live`，worker 死亡不会被识别。
- 未验证：非 Windows 平台的进程组回收、非本机用户访问被拒、daemon 升级时的协议共存、托盘与安装器联动。
- 单实例锁在 Windows 用 `Global\` 命名互斥量，多用户会话下需要按 SID 区分（当前是单用户假设）。

## 回滚

删除 `backend/app/runtime/daemon/` 与三份测试、本 ADR 及索引条目即可；`backend/` 其余模块不引用它，回滚不影响 API 与 Worker。
