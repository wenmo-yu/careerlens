# ADR 0018：Worker 与 Scheduler 的显式心跳健康语义

- 状态：Accepted（心跳表与 runtime/status 已实现；/health/ready 保持原语义）
- 日期：2026-11-28
- 相关代码：`backend/app/models/heartbeat.py`、`backend/app/runtime/heartbeat.py`、`backend/app/runtime/worker.py`、`backend/app/runtime/agent/scheduler.py`
- 相关 API：`GET /api/v1/runtime/status`

## 决定

进程存在不等于业务健康。API 存活只由 `/health/live` 表达；`/health/ready` 继续只检查数据库与检索依赖，避免在 API-only 部署中把未启动 worker/scheduler 判为不可用。

长运行组件写 `runtime_heartbeats`：

- `role` 只能是 `worker` 或 `scheduler`；
- 每次心跳写 `instance_id`、`pid`、`heartbeat_at`；
- worker 每 5 秒写一次，scheduler 在 tick 中每 5 秒写一次；
- `GET /api/v1/runtime/status` 返回每个角色的 `healthy / state / age_seconds / instance_id / pid / started_at`；
- 阈值是 `AGENT_LEASE_SECONDS * 3`，过期即 `stale`，没有记录即 `not_started`。

心跳不是业务事实：Run、事件、审批和任务树仍只由业务库决定。心跳只回答“这个后台进程是否仍在定期报活”。

## 为什么不用 Run 租约代替心跳

没有活动 Run 时租约为空，无法区分“空闲且健康”与“进程已死”。直接查询 OS 进程又会引入本机权限和跨容器不可见的问题。显式心跳表让 API-only、Worker-only 和 Scheduler-only 部署都能得到一致判断。

## 验证

- 心跳 upsert、stale 计算、未知角色拒绝均有测试。
- `runtime/status` 测试断言 `heartbeats.worker/scheduler` 存在且无记录时为 `not_started`。
- 迁移 `d3e4f5a6b7c8` 纳入完整升级链测试。

## 边界

- 心跳不证明 worker 正在成功处理任务，只证明它仍在循环。
- 时钟回拨会导致 age 负值，代码按 0 处理；多机时钟漂移不在本机 V4 范围内。
- 没有给 `/health/ready` 增加后台组件状态，避免改变现有部署的 readiness 语义。

## 回滚

删除 ADR、心跳模型/服务/写入调用、相关测试与迁移 `d3e4f5a6b7c8`，并从 runtime/status 响应移除 `heartbeats`；不影响 Run 或业务数据。
