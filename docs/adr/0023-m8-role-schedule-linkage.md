# ADR 0023：M8 角色与计划联动

- 状态：Accepted（联动实现；系统唤醒仍属验收缺口）
- 日期：2026-11-28
- 相关契约：[`agent-schedule-v1.json`](../../contracts/agent-schedule-v1.json)、[`agent-role-v1.json`](../../contracts/agent-role-v1.json)
- 相关代码：`backend/app/runtime/agent/schedule.py`、`backend/app/models/schedule.py`

## 决定

计划可选择绑定一个持久角色（`agent_schedules.role_id`）。绑定后：
- 触发在该角色的**持久会话**中运行，使用角色的 prompt，而不是计划自己的 prompt 或新建会话；
- 触发时把角色配置版本快照写入 `run.payload.role`（见 ADR 0020），因此角色工具收窄与防提权对计划触发**同样生效**；
- occurrence 记录本次使用的 `role_version`，供审计"哪次触发用了哪版角色配置"。

创建时校验角色归属当前用户、状态为 active 且有持久会话；触发时再次校验（配置可能在创建后变更），角色失效则拒绝触发并记录冲突。未绑定角色的计划行为完全不变，仍用自己的 prompt 与新建会话。

## 为什么这样设计

- 复用唯一的 Run/会话/事件链路，不新增第二套执行路径。
- 让"每周复盘角色 + 计划触发"（V4 场景 D）成为真实可运行路径，而不是两个孤立能力。
- 快照写入 payload 保证在途触发不被后续角色配置更新改变语义。

## 验证

- 绑定角色后触发：run 使用角色会话与 prompt，`payload.role.role_id` 正确，occurrence 有 `role_version`。
- 角色被暂停/归档后触发返回冲突，不产生 run。
- 未绑定角色的计划仍用原 prompt 与新建会话，`role_version` 为空。
- 迁移 `b0c1d2e3f4a5` 加列，head 一致。

## 未做与边界

- 系统唤醒与开机自启、睡眠错过的真机语义仍未做（见 ADR 0016）。
- 角色更新后已产生的触发快照不回溯修改。

## 回滚

删除本 ADR、迁移中的两列与联动分支即可；既有计划 `role_id` 为 NULL 时回到原行为，不受影响。
