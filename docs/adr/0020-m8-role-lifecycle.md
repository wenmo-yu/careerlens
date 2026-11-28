# ADR 0020：M8 持久角色生命周期与工具收窄

- 状态：Accepted（持久契约与服务端收窄已实现；真实用户配置与长期运行验收未做）
- 日期：2026-11-28
- 相关契约：[`agent-role-v1.json`](../../contracts/agent-role-v1.json)
- 相关代码：`backend/app/runtime/agent/roles.py`、`backend/app/api/routes/agent_roles.py`、`backend/app/api/routes/agent_internal.py`

## 决定

长期角色是**用户显式配置的持久边界**，不是第二套身份。一个角色绑定一条长会话（`agent_sessions`），保存一份带版本的配置：prompt、tool_allowlist、model_policy、budget、output_schema。配置更新递增 `version`，每次触发把当时的版本快照写入 `run.payload.role`，运行中不再改变。

五种模板（证据研究员、岗位分析员、学习规划员、证据审查员、职业教练）默认只有只读工具 `search_evidence` / `get_profile`。角色**不能提权**：allowlist 只能引用全局工具注册表中已存在的名字，未知工具在创建/更新时被拒绝；触发时服务端网关再次把模型的工具报价与每次工具调用同 allowlist 取交集，CLI 无法自行放宽。写工具仍走原有的审批 + digest + 幂等账本，角色不绕过审批，也没有邮件/webhook/外发工具。

角色有 `active / paused / archived` 三态。非 active 拒绝触发；撤销 actor 令牌时触发失败并把角色暂停，防止无同意的重复运行。角色本身只向自己的持久会话提交一条普通 agent turn，不创建角色、不以他人身份发消息、不执行外部动作。

## 为什么这样设计

- **一个事实源**：Run、会话、审批、产物都继续由业务库和原调度器负责，角色只提供配置与收窄，不引入第二套会话/事件。
- **收窄而非放宽**：默认 deny、显式 allow、未知工具拒绝；服务端强制而不是依赖 CLI 自觉，符合 T16/T13 的越权门禁。
- **版本快照**：运行记录使用哪一版配置，避免"改了配置导致在途 Run 行为漂移"，对应 T36 的预算/配置一致性诉求。

## 验证

- 创建角色默认只读；加入未注册工具返回 `unknown_tool`；同名冲突返回 409。
- 更新配置后 `version` 递增，旧 Run 的 payload 快照不变。
- 网关层断言：角色 Run 的工具报价与调用都被 allowlist 收窄；非 allowlist 工具返回 `tool_not_allowed`。
- 暂停/归档后触发返回 409；撤销令牌触发返回 403 且角色转 paused。
- 迁移 `e7f8a9b0c1d2` 建立 `agent_roles`，head 一致。

## 未做与边界

- 没有系统级唤醒、频道消息接入、通知与产物中心 UI（M8-04 体验包）。
- 没有把角色接入持久计划（schedule 仍使用自己的 prompt）；角色与计划的组合留待体验包。
- 没有真实用户长期配置与多周运行的质量评估；当前只有确定性测试。
- 这是应用层权限边界，不是 OS 沙箱；工具执行环境隔离仍是独立缺口。

## 回滚

删除本 ADR、契约、`agent_roles` 表及其迁移、角色 API/服务，并在网关移除 allowlist 收窄分支即可；既有 Run 的 `payload.role` 字段被忽略，不影响普通 Run。
