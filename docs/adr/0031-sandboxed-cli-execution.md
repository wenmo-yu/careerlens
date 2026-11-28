# ADR 0031：把 scheduler 的 CLI 放进 AppContainer（管道 + 运行时暂存）

- 状态：Accepted（管道路径已实测；暂存运行时在本环境无法完成，见"未验证"）
- 日期：2026-11-29
- 相关：ADR 0029（隔离矩阵）、`backend/app/runtime/sandbox.py`、`backend/tools/sandbox_stage.py`

## 问题

ADR 0029 证明了容器隔离，但 scheduler 仍用 `asyncio.create_subprocess_exec` 起 CLI。不把真实执行路径搬进容器，"高风险工具能否开放"就没有答案。

## 决定

**1. 自己起进程，不用 `asyncio.create_subprocess_exec`。** 它无法传 `SECURITY_CAPABILITIES`。新增 `sandbox.popen()`：`CreatePipe` → `STARTUPINFOEX` + 能力属性 → `CreateProcessW` → 把三个父端包成 `StreamReader`/`StreamWriter` 形状。

**2. 用线程泵喂 `StreamReader`。** Proactor 只接受重叠句柄，`CreatePipe` 的同步句柄注册 IOCP 直接 `WinError 87`；`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` 也被 `CreateProcessW` 拒绝（87）。所以读端用 `asyncio.to_thread` 循环 `read(65536)` → `feed_data`，写端用带缓冲的 shim。代价是每进程 2 个线程，池上限 6，可接受。

**3. 只让子端的三个管道句柄可继承。** 父端 `SetHandleInformation(..., 0)`；`bInheritHandles=TRUE` + `STARTF_USESTDHANDLES`。

**4. 暂存运行时。** 容器穿不过 `D:\work`（写 DACL 会触发全树传播，`icacls` 与 `SetNamedSecurityInfoW` 都会卡数分钟），因此真实部署把解释器与应用复制到 `%LOCALAPPDATA%\CareerLens\agent-runtime`，一次性授予 `(OI)(CI)(RX)`。scheduler 通过 `AGENT_SANDBOX=appcontainer` + `AGENT_SANDBOX_RUNTIME` 使用它，缺任一条件直接报错，不静默回退。

**5. 环境白名单。** 沙箱 CLI 只拿到 `PYTHONPATH`/`PYTHONUNBUFFERED`；capability 令牌走 JSONL 管道，API key 留在可信网关。主机环境里的密钥不会进容器。

## 验证

- `sandbox.popen` 在容器内跑 `cmd.exe`：stdout 正确、退出码 0（本地实测）。
- 攻击矩阵（ADR 0029）：读宿主秘密、写外部、外网、注册表、UNC 全拒；工作区与 loopback 放行。
- `tests/test_scheduler_sandbox.py`（4 项）：命令、cwd、环境、缺 runtime/不完整 runtime 的拒绝路径。
- 管道两个真坑：`_pipe` 返回 `(child, parent)`，调用处写反会让 stdout 句柄被清掉，表现为子进程 `0xC0000142`；`STARTF_USESTDHANDLES` 的三个句柄必须都是子端。

## 未验证（必须明说）

- **暂存运行时没有在本机跑通**：本执行环境的写入被限制在工作区内，复制 12k 文件到 `%LOCALAPPDATA%` 被安全删除/备份守卫拦截。`tools/sandbox_stage.py` 已实现（robocopy 等价逻辑、重命名代替 rmtree、验证用容器内 import），需要在真实安装流程里执行一次并留下 `--verify-only` 的输出。
- 因此"真实 CLI 在容器内跑完一轮 Run"尚未验收；当前只到"容器 + 管道 + 命令/环境接线"。
- 解释器授权方案选的是暂存复制，不是"给开发目录加 ACE"：后者在大目录上不可用，也会把构建产物暴露给容器。

## 回滚

`AGENT_SANDBOX=off`（默认）即回到 `create_subprocess_exec`；`sandbox.popen` 与暂存脚本不再被调用。
