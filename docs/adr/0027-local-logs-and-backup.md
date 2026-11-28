# ADR 0027：本地日志滚动与数据库备份

- 状态：Accepted（SQLite 已实现并验证；PostgreSQL 明确拒绝）
- 日期：2026-11-28
- 相关代码：`backend/app/runtime/logs.py`、`backend/app/runtime/backup.py`、`backend/tests/test_runtime_ops.py`

## 问题

桌面部署会让 API、worker、scheduler 连续跑几天。此前 worker/scheduler 只有 `logging.basicConfig`，日志进控制台，桌面场景下等于没有；而 SQLite 数据库直接拷贝文件在写入时可能得到损坏副本。

## 决定

**日志**：`logs.configure(process)` 为每个进程挂一个 `RotatingFileHandler`（`LOG_DIR`、`LOG_MAX_BYTES`、`LOG_BACKUPS`）。关键点是幂等：按进程标签移除旧 handler 再挂新的，重复调用不会叠加 handler 或重复行。`LOG_DIR` 为空时退回 stdout，CI 与单测保持安静。

**备份**：`backup.backup(url, out_dir)` 用 `VACUUM INTO` 生成一致快照（不直接复制文件），命名带 UTC 时间戳且拒绝覆盖；随后立即 `verify()` 重新打开副本，检查 `PRAGMA integrity_check`、表数量与 `alembic_version`。校验失败会删除坏产物并报错，避免留下一个看起来成功实际不可用的备份。

**PostgreSQL 明确拒绝**：返回 `BackupError` 并提示使用 `pg_dump` 或托管快照。半成品 `pg_dump` 包装比清晰拒绝更危险。

## 验证

- 快照可重新打开，`integrity_check=ok`，`alembic_version` 保留，表数量与源一致。
- 拒绝内存库、非 SQLite URL、不存在的源文件；拒绝把非数据库文件当作备份通过。
- CLI 在拒绝时返回非零码，正常路径先备份再校验。
- 日志：重复配置后该进程仍只有 1 个 handler；写入超过阈值后出现轮转文件；空 `LOG_DIR` 返回 `None` 且不创建文件。

## 未做与边界

- 没有定时备份调度、保留策略（只保留用户手动/脚本触发的产物）。
- 没有恢复演练自动化（`verify` 只证明可读与版本存在，不证明业务查询正确）。
- 没有 PostgreSQL 备份实现；没有把日志上传/聚合。
