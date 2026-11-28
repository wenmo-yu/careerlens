# ADR 0013: M5 durable tool ledger and approval/recovery loop

- Status: Accepted
- Date: 2026-11-28
- Scope: CareerLens agent plane, M5 safety slice (T11/T12/T13/T30/T34)

## Context

M3/M4 的 agent plane 已经有能力令牌、durable run、事件序号、租约与 fencing
token，但工具层只有 read 工具，审批状态只存在于内存中的 CLI 轮次。一旦 CLI 或
daemon 重启，等待批准的 tool call、文本和轮次都会丢失；即使批准成功，也没有
持久化账本证明某个写调用究竟执行了几次，重复恢复可能造成重复副作用。

本 ADR 只交付**可测试的 M5 安全切片**：持久工具账本 + 写工具审批/恢复闭环。
它不是一个完整的 OS 沙箱，也不声称隔离文件系统或网络。

## Decision

1. **数据模型与迁移**：新增 `AgentToolLedger`（`user_id/session_id/run_id/
   invocation_id/tool/args_digest/approval_id/status/result/error/created_at/
   updated_at`，`(run_id, invocation_id)` 唯一约束，状态
   `pending/succeeded/failed/denied/unknown`）和 `AgentArtifact`
   （content + JSON citations）。迁移 `b5c6d7e8f9a0` 以 `a9b8c7d6e5f4` 为
   `down_revision`，提供 upgrade/downgrade。
2. **写工具**：注册 `save_career_note`（`side_effect=write`，
   `scope=agent.artifact.write`）。handler 在单个事务内依次写 ledger `pending`
   → artifact → ledger `succeeded` + 结果（artifact id/title/evidence count）。
   同 invocation + 同 digest 返回原结果且不重复写 artifact；同 invocation 不同
   digest 返回 `tool_ledger_conflict`。`evidence_ids` 必须是当前用户已存在的
   证据 id，否则拒绝。执行失败只记录 `failed`，不伪造成功。
3. **工具网关**：`tools.invoke` 支持 `invocation_id/approval_id/approved/
   args_digest`（带默认值，兼容旧调用）。写工具必须有 invocation、批准且
   digest 与审批记录一致，否则 `approval_required/approval_mismatch`。所有
   工具继续拒绝模型提供的 `user_id/workspace_id/session_id`。
4. **审批持久化**：`store.wait_for_approval` 把 `pending_turn`（原始
   tool_calls、text、turn、args_digest）和 `pending_tool`（含 approval_id、
   args、args_digest）写入 `AgentRun.payload`；同 invocation 复用审批，digest
   不同则 `AgentConflict`。`decide_approval` 对重复 approve/deny 幂等，结果
   冲突返回 409。`AgentClaim` 增加 `payload` 字段供恢复使用。
5. **CLI 屏障与恢复**：遇到 write 工具时先 emit `approval.requested`
   （invocation_id/tool/args_digest/scope/完整 tool_calls/text/turn），停止本轮
   且不 emit `run.settled`。`run.start` 携带 `pending_tool/pending_turn` 时只
   恢复该 invocation 一次（携带 approval_id/args_digest 调用网关），随后从下
   一轮模型调用继续；已恢复的 invocation 不再触发审批也不重复执行。
6. **Scheduler 恢复校验**：重新领取时校验 `approval.status=approved` 且
   `args_digest` 与 `pending_tool` 一致，再把两者放进 `run.start` params；
   不一致则 fail（`approval_mismatch`）且不执行工具。旧 attempt/generation
   事件继续被拒绝。
7. **API/契约**：approval DTO 暴露 `args_digest/tool/scope/created_at`；
   capabilities 增加 `write_tools` 与 `tool_ledger=true`，`read_only_tools`
   只列 read 工具。`agent-runtime-v1.json` 增加写工具、ledger 状态、审批
   payload 必填字段、新错误码 `approval_mismatch/tool_ledger_conflict/
   tool_ledger_incomplete/artifact_not_found`，并明确“批准不等于重复执行”。

## Alternatives

- **只在 CLI 内存保存 pending tool call**：拒绝。进程重启即丢失，无法满足
  durable 要求。
- **批准后在 CLI 直接落库 artifact**：拒绝。CLI 不持有用户身份与事务边界，
  身份必须来自 capability，写入必须经网关。
- **每次恢复都重新执行写工具**：拒绝。会造成重复 artifact；用 ledger 做
  invocation 级幂等才是正确边界。
- **引入 Agent SDK / 通用沙箱框架**：拒绝。任务要求严格自研，且真实高风险
  工具仍禁用，无需引入外部执行框架。

## Risks

- 审批决定与 ledger 写入是两个阶段：恢复时由 scheduler 重新校验 approval
  状态与 digest，任何不一致都 fail-closed，而不是信任 CLI 缓存。
- CLI 与网关的 `args_digest` 必须完全一致：已统一到 `tools.digest_args`
  （canonical JSON + SHA256），并由测试断言。
- `pending_turn` 保存在 run payload 中；损坏或不完整的 payload 会让模型轮次
  错位。scheduler 校验失败后 fail，不会盲执行工具。
- 当前只有一个写工具；新增写工具必须各自实现 invocation 幂等与失败记账。
- 迁移在 SQLite 与 PostgreSQL 上通过 `_has_table` 守卫与 JSON 列兼容；生产
  环境仍应在灰度库上先跑一次 upgrade/downgrade 演练。

## Rollback

- 代码：回退本切片的所有改动。
- 数据库：执行迁移 `b5c6d7e8f9a0` 的 downgrade（删除
  `agent_tool_ledger` 与 `agent_artifacts`），或把 `alembic_version` 降级到
  `a9b8c7d6e5f4` 后从备份恢复。
- 回退后 capabilities 不再暴露 `write_tools`，CLI 遇到 write 工具会停在审批
  屏障（安全失败），不会静默执行。
- 已写入的 artifact 属于业务数据，回滚时应按数据保留策略处理，不自动删除。

## Testing

命令与真实输出（2026-11-28，Windows，venv `D:/work/career/.venv-careerlens`，
工作目录 `backend`）：

```
ruff check --config pyproject.toml .
All checks passed!

python -m pytest -q tests/test_agent_gateway.py tests/test_agent_store.py tests/test_agent_cli.py tests/test_agent_scheduler.py tests/test_agent_api.py tests/test_migrations.py
59 passed, 1 skipped in 28.31s
```

覆盖点：写工具无审批被拒；审批后执行一次且重复 invocation 不重复写
artifact；同 invocation 不同 digest 冲突；不存在/跨用户 evidence 被拒；
审批不匹配被拒与拒绝后不执行；重复 approve/deny 幂等且冲突 409；CLI 发出
`approval.requested` 后没有 `run.settled`，恢复后只执行一次并 settled；
scheduler 新 attempt 恢复原 invocation，digest 变化则 fail 且不执行工具；
API approval DTO/capabilities 更新；迁移 upgrade/downgrade。

## Boundaries / 未做

- **没有 OS 文件/网络 broker**：本切片不提供文件系统或网络调用能力，真实
  高风险工具（写文件、发网络请求、执行 shell）仍然禁用。
- `save_career_note` 只写数据库 artifact，不做任何外部持久化。
- 审批 UI、过期审批自动回收、同一 run 多审批并发编排不在本切片范围内。
- 这是 durable ledger + 审批/恢复闭环，不是完整 OS 沙箱。
