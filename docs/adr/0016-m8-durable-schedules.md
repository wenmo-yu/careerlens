# ADR 0016：M8 持久计划与去重触发

- 状态：Accepted（持久契约与内部触发已实现；系统级唤醒与真实用户试学未做）
- 日期：2026-11-28
- 相关契约：[`agent-schedule-v1.json`](../../contracts/agent-schedule-v1.json)
- 相关代码：`backend/app/runtime/agent/schedule.py`、`backend/app/api/routes/agent_multi.py`

## 决定

计划是**内部任务规划器**，不是外部自动化引擎。它只能为同一用户创建一个普通 agent Run；不会调用 shell、网络或任意外部服务。创建计划时保存当前主体的 token id，每次触发仍走 `require_run_actor`，令牌撤销后触发失败并把计划暂停。

每个 `(schedule_id, due_at)` 只能有一条 occurrence 行。这个唯一键是跨重启、跨进程、跨手动/自动触发的幂等边界。自动触发推进 `next_due` 到严格大于当前时刻的下一档；错过超过两个间隔时，`skip` 策略只写 skipped 行，`run_once` 最多补一次。

手动触发使用 Idempotency-Key（数字时间戳）或 `now` 作为 `due_at`，不能绕过 actor 授权。`paused` 与 `disabled` 都拒绝触发；区别是前者可由用户恢复，后者表示计划已结束。

## 为什么不用系统定时器

Windows 任务计划程序、cron 或云函数会引入第二套身份和事实源，也难以与业务库的租约、审批、代际和账号删除回执对齐。当前方案让计划触发与普通 Run 共用同一条持久链路，所以撤销、隔离、审计和重放规则一致。代价是没有系统级唤醒：应用未运行时不会自行触发；这必须如实记录，不能当作“后台常驻计划”完成。

## 验证

- 创建 → 触发 → 重复触发返回同一 occurrence；`next_due` 单调推进。
- 暂停后触发返回 409。
- `skip` 策略下 9000 秒后的触发产生 `skipped`，不创建 Run。
- 迁移 `c7d8e9f0a1b2` 验证 head 一致。

## 未做与边界

- 没有 Windows 唤醒/开机自启的实际注册；休眠错过的语义只覆盖“恢复后按策略处理”，不覆盖唤醒本身。
- 没有 DST 时区库，只有固定间隔和 UTC 时间戳；`timezone` 字段目前是记录用途。
- 没有计划任务的用户通知/邮件/外部 webhook；这是有意的安全边界。

## 回滚

删除本 ADR、契约、计划 API/服务及迁移中的 schedule 两张表即可；既有 agent Run 不依赖 schedule 行。
