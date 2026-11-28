# ADR 0024：M8 唤醒感知与错过策略对账

- 状态：Accepted（策略对账层已实现；真实 OS 唤醒/开机自启未做，需真机）
- 日期：2026-11-28
- 相关契约：[`agent-wake-v1.json`](../../contracts/agent-wake-v1.json)
- 相关代码：`backend/app/runtime/agent/wake.py`、`backend/app/api/routes/agent_wake.py`

## 决定

把"睡眠/停机错过的计划"拆成两层：**错过策略对账层**（本 ADR 实现）与**OS 唤醒层**（未实现，需真机）。

对账层接受一个明确的 `[last_seen, now]` 时间窗（闭区间，以覆盖恰好在停机起点到期的计划）。它找出 `next_due` 落在窗口内的 active 计划，逐个交给普通 `schedule.trigger` 处理——misfire 的 `skip/run_once` 策略与 `(schedule_id,due_at)` 幂等仍由 schedule 唯一负责，不重复实现。每次对账写一条 `agent_wake_reports`（窗口长度、错过数、触发数、跳过数），作为可解释的诊断证据，不是业务事实。

**自动接入**：scheduler 启动时（`AgentScheduler.startup()`）先读取上一次 scheduler 心跳，用 `[上次心跳, 当前时刻]` 作为停机窗口对账，然后才写入自己的心跳。因此"应用关闭一段时间后重开、错过的计划被按策略补偿"是真实生效的路径，而不是只能手工调用的接口。对账失败只记日志，不阻止调度器启动。

对账接口需 `manage` 权限（会入队 run），报告读取需 `read`。它不注册任何系统定时器，不假定机器真的睡过，也不声称应用关闭期间能运行。

## 为什么不全量实现 OS 唤醒

Windows 任务计划/唤醒定时器会引入第二套身份与事实源，且需要真机睡眠/唤醒、DST 与开机自启验收，当前环境无法证明。把策略对账做扎实，能让"恢复后如何处理错过的计划"变得可解释、可测试；OS 唤醒作为独立前置缺口保留。

## 验证

- 正常/反向窗口：反向窗口返回冲突，不写报告。
- 错过的 due 被对账：skip 策略产生 skipped、run_once 产生 claimed，计数正确。
- 重复对账同一窗口不产生重复 run（依赖 schedule 幂等）。
- scheduler 启动时自动以"上次心跳 → 现在"为窗口对账，重启后产生 1 条报告与 1 个补偿 occurrence。
- 报告可被 read 角色列出，reconcile 需 manage。
- 迁移 `c1d2e3f4a5b6` 建立报告表，head 一致。

## 未做与边界

- 没有 Windows 唤醒定时器、开机自启、通知投递、DST/时区库。
- 只在进程启动时对账，运行期间不检测系统睡眠（无唤醒事件源）。
- 报告不证明真实睡眠发生，只是给定窗口的对账结果。

## 回滚

删除本 ADR、契约、`agent_wake_reports` 表及迁移、对账 API/服务即可；既有计划与 occurrence 不受影响。
