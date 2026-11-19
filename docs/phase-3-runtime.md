# 第三期：后台运行、恢复与多 Agent

第三期依赖已经打通的来源块、Wiki 版本、岗位匹配和报告服务。沿用原方案的 SaaS 形态：PostgreSQL 管队列，独立容器运行 Worker；不引入桌面进程模型或 ACP。以下四组可分别验收。

| 范围 | 实现与验收 |
| --- | --- |
| Run / Step / Event | 7 种状态，持久化步骤与有序事件；HTTP 查询、SSE 重放、工作台任务列表和结果入口。 |
| Worker 与幂等 | 同用户串行、不同用户有界并行，数据库领取；相同键同输入复用，冲突返回 409；提交前检查租约代次、来源/画像代次和页面版本。 |
| 多 Agent | Coordinator 按类型顺序调用岗位要求分析、Wiki 整理或报告撰写，以及只读引用核验。基于独立 LangGraph 子图；程序投影数据范围，角色不能自由调用外部工具或直接写库。 |
| 恢复和隐私 | 租约超时后重新领取，计算可以重跑，提交与终态/事件同事务。支持用户确认、主动取消、账号清理；向量写入有持久化补偿。 |

## 使用与 API

1. 启动 Compose；等待数据库迁移、API 和 Worker。工作台上传文档/媒体、提交岗位分析、编译 Wiki 或生成报告后，会跳到「后台任务」。Wiki 可勾选先确认再执行。
2. 在任务中心选择一条记录。运行期间可取消，等待确认时可拒绝；成功后可打开岗位分析、报告或 Wiki。关闭页面不会取消，重新进入可回放记录。
3. API 可用 `POST /api/v1/runs` 提交 JSON，并建议带 `Idempotency-Key`（1–128 字符，同一逻辑动作重试时复用）。JSON 使用 `user_id`、`operation` 和 `input`：`job_analysis` 传 `title/jd_text/weekly_hours`，`wiki_compile` 传 `slug/title/evidence_ids` 和更新时的 `base_version`，`report` 传 `job_analysis_id`。需要审批时加 `requires_confirmation: true`。
4. `POST /api/v1/runs/uploads` 接受 multipart `upload`、`user_id`、可选 `media` 和 `requires_confirmation`。GET `/runs`、`/runs/{id}`、`/steps`、`/events`、`/stream` 按用户查询；向单个 run 的 `/decision` POST `{"approve":true}` 或向 `/cancel` POST 可修改状态。启用鉴权时分别使用 `read`、`write` 权限和 Bearer Header。
5. SSE 可携带最后收到的整数序号 `Last-Event-ID`（或 `after_seq`），服务器只发送后续事件。用 `(run_id, seq)` 去重。连接终止时可通过 GET 获取最新状态；游标高于当前记录返回 409。

同步入口仍兼容原来的 API 与 MCP。短对话继续使用原有 LangGraph 会话；后台运行不把聊天历史或令牌交给专业 Agent。

## 恢复、取消和数据边界

- 状态：`queued → running → succeeded/failed`；`waiting_confirmation` 不占执行槽；`interrupted` 可被重新领取。取消已提交的任务不会撤销业务结果，也不会丢失已成功提交的报告版本。
- 领取和续租带代次。提交首先重验原提交令牌权限、输入代次及 Wiki 版本，再在短事务中同步写业务记录、终态和最终事件。未提交时可以拒绝或取消；PDF/媒体解析由可终止的子进程执行，取消不能撤回已经发往外部模型的请求。
- Worker 退出后，未完成的计算可重新执行，最多尝试三次。这是基于数据库步骤和提交边界恢复，不是对模型响应逐 token 续跑；专业 Agent 的当前上下文不持久化，已提交业务不重放。可重复模型调用可能计费。
- 进度事件不保存原文、模型响应或令牌。原始上传仅暂存在未结束的 Run 里；结束、取消、过期或账号删除时清除。运行记录会保留到账号清理；备份遵循站点的保留策略。
- 向量索引和删除按 Evidence ID 写入 outbox，同一条目的操作串行，失败使用退避重试。查询使用 PostgreSQL 的有效内容，已删除的向量不会当成有效证据。账号删除的向量清理可能显示为排队；历史报告和对话快照的证据撤销策略不因此改变。

## 部署与验收

- 在生产环境先运行 Alembic 迁移，再更新 API 与 Worker；两者必须共享数据库与相同权限模式。Compose 默认启动 Worker；非 Compose 在后端环境运行 `python -m app.runtime.worker`。
- 默认每用户 1 个执行槽、12 个未完成任务，集群 4 个执行槽、每 Worker 2 个并行；每次尝试 300 秒，租约 30 秒，排队或待确认期限 24 小时。见环境模板中的 `RUN_*` 参数。上传大小还受原 API 单文件上限和反向代理限制。
- Worker 默认内存上限 2 GiB，无公开端口。启用真实 Qwen/OCR/ASR 时使用对应 Compose overlay，按设备和模型提高 `RUN_WORKER_MEMORY`；扫描 PDF 仍按待 OCR 页处理，真实 OCR/ASR 质量要在目标环境验收。
- `pytest tests/test_run_runtime.py` 验证双领取、断线重放、用户隔离、取消竞态、过期代次、提交中断恢复、outbox 和账号删除；`docker-smoke.ps1` 在 Quality Gate 中通过两个 Worker 实例验证真实 PostgreSQL 上的后台报告、Wiki 审批、取消和 SSE。
