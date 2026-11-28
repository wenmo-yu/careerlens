# ADR 0015：M6 多任务树、角色隔离与结果投影

- 状态：Accepted（持久化契约与 API 已实现；真实模型下的多专家质量评测未做）
- 日期：2026-11-28
- 相关契约：[`agent-multi-v1.json`](../../contracts/agent-multi-v1.json)、[`agent-runtime-v1.json`](../../contracts/agent-runtime-v1.json)
- 相关代码：`backend/app/runtime/agent/multi.py`、`backend/app/api/routes/agent_multi.py`

## 决定

### 1. 任务树而不是共享聊天室

一个团队由一个父任务和最多三个子任务组成。每个子任务拥有独立的 `agent_sessions` 行与 `executor_kind=agent` 的 Run，因此子任务的历史不进入父任务或兄弟任务。父任务只是协调行，永不调用模型。

### 2. 角色工具范围

`researcher` / `reviewer` / `synthesizer` 只绑定只读工具白名单。范围存在任务行和契约中，由网关按 capability 与注册表执行；模型不能通过参数提升角色权限。M5 的写工具默认不授予子任务。

### 3. 结果投影与引用核验

父任务只看到每个子任务最多 2000 字符的摘要与引用列表。引用先与当前 `user_id` 的 `evidence` 表核对：不存在的引用进入 `unverified_citations`，不会作为可信证据传给父任务。被截断的结果标记 `truncated`。

### 4. 团队邮箱

消息按 `(team_id, message_key)` 唯一。重放同一载荷返回原消息；同 key 不同载荷返回 409。这是交付去重，不是消息总线；收件人从持久表读取，不依赖进程内存。

### 5. 预算与取消

`agent_task_budget_use` 按任务累计 attempts、input/output tokens 和估算成本；重启不会重置。取消父任务会级联取消子任务及它们尚未终态的 Run，并写 `run.cancelled` 事件。父任务在所有子任务终态时才投影结果，等待者不占模型 slot，因此不会死锁。

## 未做与边界

- 没有实现 Team 实时推送、子任务向父任务回写消息、或基于质量指标的动态专家路由。
- 没有真实模型的 60 例合成评测，因此不能声称多 Agent 已稳定提升答案质量。
- 角色工具范围目前只到工具注册表；OS 文件/网络 broker 仍未实现。
- 预算数字来自 provider usage；usage 缺失时保持为 0 并标记为未知，不用估算冒充真实值。

## 验证

- 6 项 M6/M8 测试覆盖：三个子任务独立 session/run、团队邮箱幂等和冲突、父取消级联、引用核验与截断、计划触发幂等、错过策略。
- 迁移 `c7d8e9f0a1b2` 从 M5 ledger head 升级并回退；`test_migrations.py` 验证 head 一致。

## 回滚

删除本 ADR、契约、M6 路由/模型/服务及迁移 `c7d8e9f0a1b2` 即可；M0–M5 的 Run 与会话表不受影响。
