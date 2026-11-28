# ADR 0029：Agent CLI 的 AppContainer 执行边界（T14/T16）

- 状态：Accepted（隔离已实测通过；与 scheduler 的管道接线未做）
- 日期：2026-11-28
- 相关证据：[`appcontainer-attack-matrix.json`](../evidence/appcontainer-attack-matrix.json)
- 相关代码：`backend/app/runtime/sandbox.py`、`backend/tools/sandbox_probe.py`

## 问题

工具审批与文件 broker 都是**应用层**边界：只要代码走到 `open()` 或 `socket`，边界就失效。V4 要求 MCP 与 CLI 在受限容器里运行，网络默认 deny。这必须由操作系统保证，而不是我们自己的 if 判断。

## 决定

用 **AppContainer + 无 capability** 启动子进程：

- 无 `internetClient`：出站网络由 OS 拒绝；
- 文件系统只授予工作区（`(OI)(CI)(M)`），其余路径默认拒绝；
- HKCU 写入、UNC/管理共享读取默认拒绝；
- 按 SID 做 **loopback 豁免**，让 CLI 仍能访问本机 API（`127.0.0.1`），外网依旧封闭；
- 子进程环境从白名单构造（`SystemRoot`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA` 等），密钥类变量不继承。

实现要点（都是踩过的真坑）：

1. `CreateProcessW` 传 UTF-16 环境块必须带 `CREATE_UNICODE_ENVIRONMENT`，否则 `ERROR_INVALID_PARAMETER (87)`。
2. 环境块缺少 `USERPROFILE`/`APPDATA`/`LOCALAPPDATA` 时，AppContainer 内启动会失败并返回 `ERROR_ENVVAR_NOT_FOUND (203)`。
3. 所有 Win32 调用必须显式声明 `restype`/`argtypes`；不声明 HANDLE 返回值会在 64 位被截断。
4. 捕获输出不能只用 `GENERIC_WRITE` 打开再读同一文件（写句柄独占导致 `PermissionError`）：需 `FILE_SHARE_READ|FILE_SHARE_WRITE`，并在读取前关闭宿主句柄。
5. **不要沿父目录链授权**：`icacls` 在大目录（`node_modules`、用户目录）上会触发继承传播，耗时以分钟计，且本机 `C:\Users\momo\.workbuddy` 是指向 D 盘的 junction，会走进另一棵大树。实测只需授权叶子目录即可（用户 Temp 默认可穿越）。
6. 探针子进程用 PowerShell 而不是 Python：`%SystemRoot%\System32` 对 AppContainer 默认可读，因此探针**不需要**给解释器授权，避免了"用自己的 ACL 证明自己安全"。

## 实测结果（提权后，2026-11-28）

| 探针 | 期望 | 实测 |
| --- | --- | --- |
| 读工作区外的秘密文件 | 拒绝 | `UnauthorizedAccessException` |
| 写工作区外 | 拒绝 | `UnauthorizedAccessException` |
| 写工作区 | 允许 | 成功 |
| 外网 1.1.1.1:443 | 拒绝 | 连接失败 |
| 回环 127.0.0.1 | 允许 | 成功（loopback 豁免生效） |
| HKCU 注册表写入 | 拒绝 | `UnauthorizedAccessException` |
| UNC `\\127.0.0.1\C$` | 拒绝 | 不可达 |
| 环境泄漏 `AI_API_KEY` | 无 | 无 |
| 子进程 | 观察项 | 可创建（Job Object 负责限制） |

`violations: []`，报告存于 `docs/evidence/appcontainer-attack-matrix.json`（SID 已脱敏）。loopback 豁免需要管理员；未提权时该项会失败并如实记录，探针不会降级为"通过"。

## 为什么子进程仍允许

AppContainer 管的是资源访问，不是进程数量。V4 的"限制 spawn"由 Job Object 的 `ACTIVE_PROCESS` 承担（M0 已验证）。两者是不同层，不能互相替代。

## 未做与边界

- **scheduler 仍用普通子进程 + JSONL 管道**跑 CLI。要把它搬进容器，需要 `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` 精确继承 stdin/stdout 管道句柄；当前 `sandbox.run` 是一次性执行（输出落临时文件），没有长连接管道。这是明确的下一步，不是已完成项。
- 真实 CLI 需要读解释器与 venv：要么在安装期一次性 `icacls /T` 授权（慢，但只做一次），要么把运行时发布到由 `ALL APPLICATION PACKAGES` 可读的位置。两者都未实现。
- 未验证：注册表其他 hive、命名管道、COM、剪贴板、驱动/设备访问、嵌套容器。
- 未做网络目标的细粒度允许列表（除 loopback 外全 deny，没有"只允许某域名"）。

## 清理语义

探针只撤销自己添加的 ACE（`grant_chain` 返回的列表）并删除 profile。若进程被强杀，可能留下指向该容器 SID 的孤儿 ACE；它的实际风险很低（profile 删除后无法再生成对应 token），但 `icacls /remove:g` 在大目录上同样会触发继承传播，可能耗时数分钟甚至卡住，所以不做自动清扫，也不建议在无人值守脚本里对用户目录批量清理。

## 回滚

删除本 ADR、`sandbox.py`、探针与证据文件即可；没有任何生产路径依赖它，因此回滚不影响现有 Run。
