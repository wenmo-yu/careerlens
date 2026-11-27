# 数据模型与证据生命周期

核心原则：职业结论不是一段独立生成的文字，而是能够回到用户授权来源的结构化记录。以下模型位于 [`backend/app/models/`](../backend/app/models/)，读者可以用 Evidence ID 从画像、岗位分析和报告追溯原始内容。

## 领域关系

```mermaid
flowchart LR
  U[User] --> S[SourceDocument<br/>文件 / 链接 / 令牌]
  S --> B[ParsedBlock<br/>页码 / 段落]
  B --> E[Evidence<br/>去重正文 + ID]
  E -. 多来源定位 .-> S
  E -. evidence_ids .-> P[ProfileItem]
  P --> J[JobAnalysis]
  J --> R[CareerReport]
  E --> W[WikiPage 引用]
  E --> Q[Qdrant 索引]
  U --> T[ConversationThread]
  T --> C[ConversationMessage]
  U --> PP[ProfileUpdateProposal]
```

这张图表达业务引用关系，不表示所有关联都由数据库外键直接约束。`evidence_ids` 和分析明细中存在 JSON 数据，因此调用方仍须校验引用是否属于当前用户、是否仍存在。

| 对象 | 主要内容 | 作用 |
| --- | --- | --- |
| `Evidence` | 用户、来源类型/名称/外部 ID、正文、元数据、时间 | 唯一原始证据单元；长内容会分块 |
| `ProfileItem` | 类别、名称、熟练度、置信度、`evidence_ids`、详情 | 可查询、可修正的长期画像；同一用户/类别/名称有唯一约束 |
| `JobAnalysis` | JD 文本、要求、匹配项、缺口、学习路径、报告 JSON | 一次岗位决策的结构化快照 |
| `CareerReport` | 版本、Markdown、结构化内容、诊断、`is_stale` | 独立报告版本，不覆盖旧报告 |
| `ProfileUpdateProposal` | 待批准的画像变更 | 将用户聊天中的纠正与长期资料写入分开 |
| `ConversationThread` | 对话线程与用户归属 | 限定历史会话的访问范围 |
| `ConversationMessage` | 角色、正文、意图、会话 ID、时间和引用来源 | 保存多轮上下文，支持删除证据时清理受影响的回复 |
| `AccessToken` / `AuditEvent` | Token 哈希/Scope、操作审计 | 权限与隐私操作追踪；不存明文 Token |

除核心对象外，隐私导出与账号删除还统一覆盖下列扩展数据；引用字段与数据库关系以 [`backend/app/models/`](../backend/app/models/) 为准，导出范围见 [`services/privacy.py`](../backend/app/services/privacy.py)：

| 对象 | 职责 | 边界 |
| --- | --- | --- |
| `SavedJob` | 用户保存的 JD 原句、优先级与备注 | 对比接口返回最近三份；规则分仍需逐份分析 |
| `LearningProgress` / `LearningPlan` | 周计划、状态、作品与验收方式 | 进度只能关联当前用户已存在的 Evidence，不新增能力事实 |
| `UserConstraint` | 约束条件与画像展示偏好 | 不改事实画像与岗位匹配分 |
| `DimensionDefinition` / `ProfileExtension` | 用户自定义维度与扩展画像字段 | 与内置画像条目分开存储 |
| `AssessmentResult` | 自陈量表结果与元数据 | `source=self_report`，单独保存，不进入事实画像或匹配分 |

画像条目的 `confidence` 是规则排序值。规则抽取会合并同一个来源文档的切块。模型候选须附能在证据中找到的引文，候选值不采用模型报出的熟练度和置信度。判断能力仍需读原文并核对支持范围。

## 写入与派生

1. 文本、文件、平台导出或多模态转录先在 [`ingestion/`](../backend/app/ingestion/) 中解析，再由 [`services/evidence.py`](../backend/app/services/evidence.py) 标准化、分块并写入 Evidence。相同正文可共用一条 Evidence，同时保留多个 SourceDocument / ParsedBlock 定位；只有用户主动提供或授权导出的内容才应进入系统。
2. Evidence 数据库提交后建立 Qdrant 索引。两者不是分布式事务；若向量写入失败，数据库记录仍可能存在，可检查导入诊断并调用 reindex 修复。
3. [`services/profile.py`](../backend/app/services/profile.py) 读取用户 Evidence 构建画像。默认规则提取适合可复现演示，配置真实生成模型后可抽取更丰富的类别；模型输出仍会过滤无效 Evidence ID。
4. [`services/jobs.py`](../backend/app/services/jobs.py) 从 JD 提取技能要求，并与当前画像对照。`strong / partial / gap` 是规则分级，不是统计意义的招聘成功概率；学习路径根据缺口、已有等级、目标岗位和每周时间给出有边界的估算。
5. [`services/reports.py`](../backend/app/services/reports.py) 将画像与指定 JD 分析固化为新版本报告。模型可在允许的证据边界内补充叙述，失败时仍有确定性报告。

## 用户纠正与陈旧数据

用户在对话中说“我现在更希望去做后端”时，不应把这句话自动当成确认事实。系统会先生成 `ProfileUpdateProposal`；批准后在同一数据库事务内写入修正 Evidence、更新画像并把草案标记为已批准，任一步失败都会整体回滚，拒绝则不改变长期画像。画像重建会保留已经确认的更新项，但当前实现并不是通用的冲突消解或事实版本系统：如果原始资料仍支持旧条目，删除型修正后续仍需检查重建结果。

删除 Evidence 会清除受影响的历史报告正文、分析结果及聊天回复。普通过期的历史报告可以继续查阅。整账号删除提交后停用账号并撤销全部 Token，回执报告向量和旧检查点清理进度。部署侧的备份和外部服务保留期使用各自的清理机制。 [接入、MCP 与安全](integrations-and-security.md)

## 可复现性与检查点

- 数据库 schema 由 [Alembic 迁移](../backend/migrations/)管理；Docker 的独立 migration job 先于 API/MCP 启动。
- Qdrant 索引是派生状态；变更 Embedding 维度或模型后，应使用新 collection 或重建索引，避免混合不同向量空间。
- `ConversationMessage` 是对话历史的来源。LangGraph 在本次请求中运行，旧版保存的 checkpoint 由隐私清理任务处理。
- 想检查某项岗位结论，按 `JobAnalysis → ProfileItem → evidence_ids → Evidence` 路径验证。想检查对话答案，则直接展开回答中引用的 Evidence 并查看检索诊断。
