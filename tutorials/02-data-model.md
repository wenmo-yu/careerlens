# 02 · 数据模型：三张核心表

**目标**：理解 CareerLens 用哪三张表撑起"证据可追溯、画像可纠正、长任务可恢复"，以及为什么这样设计。

**前置**：完成[第 01 篇](01-quickstart.md)；能读懂 SQLAlchemy 的 `Mapped[...]` 声明。

**对应源码**：`backend/app/models/`

---

## 三类数据，三种职责

CareerLens 的数据分三层，职责边界刻意分开：

| 层 | 表 | 回答的问题 | 关键字段 |
| --- | --- | --- | --- |
| 证据层 | `Evidence` | "这句话从哪来？" | `user_id`、`content`、`source_type`、`content_hash` |
| 画像层 | `ProfileItem` | "我知道你什么？凭什么？" | `category`、`name`、`level`、`confidence`、`evidence_ids` |
| 运行时 | `AgentRun` / `RunStep` / `RunEvent` | "长任务现在到哪了？" | `status`、`idempotency_key`、`generation`、`seq` |

PostgreSQL 是唯一业务数据源；Qdrant 只是 `Evidence` 的可重建检索索引。这个分离是后面所有设计的地基。

## 证据层：Evidence

一条 Evidence 是一次用户授权内容的标准化结果：

```python
class Evidence(Base):
    id: str                    # 稳定 ID，被画像和引用系统使用
    user_id: str               # 用户隔离
    source_type: str           # self_statement / resume / personal_media ...
    source_name: str           # 来源名，去重时作为来源标识
    content: str               # 正文
    content_hash: str | None   # 规范化文本的 sha256，用户级去重键
    source_metadata: dict      # 位置、时间、多来源引用等
    chunk_index: int           # 同一次导入的分块序号
```

两个设计点值得注意：

1. **`content_hash` + `(user_id, content_hash)` 索引**：重复导入同一段文本时复用原 Evidence，把新来源追加到 `source_metadata["sources"]`，而不是新建一行。否则重复上传会虚增画像置信度。
2. **`source_metadata` 保留结构信息**：解析层给出的页码、bbox、时间戳都存在这里，供后续 Wiki 引用和核验使用。

去重逻辑的单一入口在 `services/evidence.py::create_evidence_chunks`——所有导入（文本、文件、媒体、Connector）都走它。

## 画像层：ProfileItem

```python
class ProfileItem(Base):
    user_id: str
    category: str        # skill / experience / interest / target_role / preference
    name: str
    level: int           # 1-5
    confidence: float
    evidence_ids: list   # 支撑该条目的 Evidence ID
    details: dict
```

**`evidence_ids` 是整个系统的信任锚**。画像条目不能凭空出现；构建时从 Evidence 抽取，每条都带回证据 ID。岗位匹配时同样只使用当前仍有效的证据——证据被删，画像引用和报告会相应失效或标记 stale。

画像修正不直接写这张表，而是先生成 `ProfileUpdateProposal` 草案，用户确认后才由 `decide_proposal` 修改；被删除的条目写入 `ProfileSuppression` 墓碑，避免下次 rebuild 从旧证据里"复活"。

## 运行时：一次长任务的三种记录

`AgentRun` 是一次任务，`RunStep` 是它的步骤，`RunEvent` 是有序进度事件：

```
AgentRun (queued → running → succeeded/failed/cancelled)
   ├── RunStep  (每个步骤的状态与结果)
   └── RunEvent (seq 递增的事件流，SSE 用它做断点续看)
```

关键字段：

- **`idempotency_key`**：同一逻辑动作重试返回同一个 run，避免重复计费和重复副作用。
- **`generation` / fencing 代次**：领取、取消、中断都会递增；提交前校验代次，过期 worker 的旧回调不能污染新状态。
- **`RunScope`**：记录输入/删除/画像的代次，提交前二次校验，防止用过期输入产出脏结果。

这套设计让"计算可以重跑，但提交必须原子"成为可能：业务记录、终态、最终事件在同一事务写入。

## 迁移：从代码到数据库

模型变化必须通过 Alembic 迁移落地：

```powershell
cd backend
python -m app.migration_runner      # 全新库执行 alembic upgrade head
```

项目有一个兼容细节：`migration_runner` 检测到旧版用 `create_all()` 建好的库时，会先补齐新表并写入 Alembic revision，再交给迁移链管理。生产环境务必设 `AUTO_CREATE_SCHEMA=false`，让 schema 只由迁移控制。

当前迁移链 head 为 `b8c9d0e1f2a3`，注册 21 张表。

## 验收清单

- [ ] 能说出 Evidence / ProfileItem / AgentRun 各自的职责
- [ ] 解释为什么画像条目要带 `evidence_ids`
- [ ] 解释重复导入为什么不该新建 Evidence
- [ ] 说明 `idempotency_key` 和 `generation` 分别防什么问题
- [ ] 在本地跑一次 `python -m app.migration_runner` 且不报错

## 下一步

数据模型清楚了。下一篇解析层（原始文件如何变成带位置的 Evidence）正在编写中，可先按[教程总览](README.md)里的"对应源码"一栏探索 `backend/app/ingestion/`。
