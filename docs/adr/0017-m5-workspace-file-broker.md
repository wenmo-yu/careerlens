# ADR 0017：M5 工作区文件 broker 与路径授权

- 状态：Accepted（文件边界已实现并测试；不是完整 OS 沙箱）
- 日期：2026-11-28
- 相关契约：[`agent-file-broker-v1.json`](../../contracts/agent-file-broker-v1.json)、[`agent-runtime-v1.json`](../../contracts/agent-runtime-v1.json)
- 相关代码：`backend/app/runtime/agent/file_broker.py`、`backend/app/runtime/agent/tools.py`

## 决定

Agent 的文件读写必须经过单一 broker，不能直接使用模型提供的绝对路径或任意用户目录。

1. **显式工作区**：`AGENT_WORKSPACE_ROOT` 为空时 `read_workspace_file` 与 `write_workspace_file` 都拒绝，默认关闭。
2. **路径白名单**：只接受非空、相对、POSIX 风格路径；拒绝 `..`、`.`、反斜杠、冒号、NUL、UNC `//`、绝对路径与 ADS。
3. **解析后验证**：检查每个现有父组件与候选文件是否是符号链接，解析后仍必须位于 root 内，且只能是普通文件。
4. **扩展与体积**：默认只允许 `.txt/.md/.json/.csv`，默认 1 MiB 上限；UTF-8 严格解码，超限或非法编码都明确失败。
5. **写操作审批与账本**：`write_workspace_file` 是 side-effect=write 工具，走 M5 approval/digest 屏障。同一 `(run_id, invocation_id)` 同 digest 返回已存结果，不重复写；不同 digest 报 `tool_ledger_conflict`；未完成账本报 `tool_ledger_incomplete`。
6. **原子写入**：先写 root 内的临时文件，fsync 后 `os.replace`，不在 root 外落盘；parent symlink 在写完前再次检查。

## 为什么不是完整沙箱

- 没有 AppContainer/沙箱进程；broker 只是应用层约束，恶意本机进程仍可绕过。
- 网络、shell、可执行文件和任意绝对路径仍不可用，但没有做真实 OS 级攻击矩阵。
- 测试环境不能创建符号链接时会跳过 symlink 用例；CI 在 Linux 上覆盖该分支。

## 验证

- 12 项新增测试覆盖：合法读写、路径穿越、绝对路径、UNC、ADS、反斜杠、`.` 段、扩展名、缺失文件、超大文件、审批缺失、幂等重放、digest 冲突与符号链接父目录。
- `tests/test_agent_api.py` 的 capabilities 断言更新为 3 个只读工具与 2 个写工具。
- 本机 Windows 对 symlink 用例返回 `pytest.skip`，不是断言失败。

## 回滚

删除本 ADR、`contracts/agent-file-broker-v1.json`、`file_broker.py`、两个工具注册与对应测试，并恢复 capabilities 断言；无需数据库迁移。`AgentToolLedger` 继续服务 `save_career_note`。
