# ADR 0011：M4 Runtime Manager（预热、租约、代际与准入）

- 状态：Accepted（池与调度原型进入 `backend/`；资源指标与自适应未做）
- 日期：2026-11-27
- 相关契约：[`agent-runtime-v1.json`](../../contracts/agent-runtime-v1.json)
- 相关代码：`backend/app/runtime/agent/pool.py`、`backend/app/runtime/agent/scheduler.py`

## 决定

### 1. 池状态机

`spawning → warm → binding → ready → running → waiting → draining → terminated`，异常进入 `faulted`。只有 `warm` 能被 `reserve`；`reserve` 一次性写入 `session_id/generation/run_id`，之后：

- 绑定壳不回到 warm，也不跨会话复用；
- Run 结束、TTL 到期或调度器关停时 `draining → terminated`，进程被杀；
- `session_id` 在终止后保留用于审计，不被清空复用。

### 2. 进程预算

`total_cap` 同时约束 spawning、warm 与 bound；`warm_target` 只控制预热数量。池不会为了补 warm 而突破总上限，活跃 Run 的绑定壳优先于预热。

### 3. 租约与 fencing

- DB 的 `lease_owner/lease_until/fencing_token` 是执行权唯一来源；心跳按租约 1/3 续期，续期失败即停。
- 每次领取 `fencing_token + 1`；事件与结算都必须带当前 token。
- `runtime_generation` 在每次绑定会话时递增；CLI 事件里的代际与绑定不一致时整轮作废并按失败重试，不写入新事实。
- Scheduler 重启时，上一进程遗留的非终态 slot 一律标 `faulted`，不信任其 pid。

### 4. 准入与公平

- 全局同时执行的 agent Run 上限 `agent_max_running`（默认 2）。
- 同一会话同一时刻只允许一个执行中的 Run；不同会话可并行。
- 队列按 `created_at, id` 先进先出，避免后来的大用户插队；用户级 pending 上限防堆积。
- 无可领取 Run 时立即返回，不占并发槽；领取失败不永久占用会话锁。

### 5. 退避与补充

进程丢失后 `faulted` 并计算 1/2/4/8/16 秒带抖动的下一轮补充时间；补充失败继续累计。预热 TTL 10 分钟、空闲绑定 5 分钟，可由配置覆盖。

### 6. 资源仪表盘

`GET /api/v1/runtime/status` 从数据库聚合：slot 状态计数、agent Run 状态计数、待审批、过期租约；`GET /api/v1/runtime/capabilities` 返回协议、执行器类型、模型 provider 与池/租约上限。两者都不依赖 daemon IPC，API 与调度器可以分别重启。

## 启动与默认关闭

调度器入口 `python -m app.runtime.agent.scheduler` 要求 `AGENT_RUNTIME_ENABLED=true`，否则以退出码 1 拒绝启动，避免升级后在未配置的部署里悄悄多跑一个进程。API 与 worker 不受影响。

## 证据

- 纯状态机测试：reserve 原子性、已绑定壳不可回池、总进程上限、非法迁移、warm/空闲绑定 TTL、退避序列与 16 秒封顶。
- 调度器测试（真实子进程 + 假 CLI）：
  - 两个并发独立会话均 `succeeded`，事件顺序含 `run.acknowledged → run.settled → run.committed`；
  - 6 个排队 Run 在准入 2、总进程 4 的约束下全部完成，结束时无活跃 slot；
  - 首次崩溃后自动重试，`attempts=2` 成功，并记录 `run.interrupted`；
  - 旧代事件连续 3 次被拒后 Run `failed / stale_generation`，从未出现 `run.committed`；
  - 长任务超时按 `cli_timeout` 重试并耗尽；
  - 调度器启动会把遗留 slot 标 `faulted`，关停会杀掉全部子进程。
- 契约一致性测试：`agent-runtime-v1.json` 的 pool states 与 `pool.py` 常量一致，Run 事件种类与 `store.RUN_EVENT_KINDS` 一致。

## 未做与边界

- 没有采集真实 CPU/私有工作集/句柄数；当前“资源仪表盘”是状态计数，不是 OS 指标。
- 没有按低内存自动把 warm 降到 0，也没有按 provider 分配模型并发槽。
- 没有多工作区权重、优先级抢占或长任务让位；公平性目前是 FIFO + 每会话互斥。
- 压力测试是 6 个假 CLI 任务，不代表真实模型延迟下的吞吐。
- 池状态写库用于诊断，不是调度正确性的唯一来源；调度仍以 Run 行与租约 CAS 为准。
