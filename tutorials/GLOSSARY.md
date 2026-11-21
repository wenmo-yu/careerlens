# 术语表

术语第一次出现时，正文会先用一句话解释；这里按层集中索引，方便随查。**不用一次背完**——遇到时回来查对应条目即可。每条给出「人话解释 → 在代码里的位置 → 在哪篇用到」。

## 概念层：这套系统怎么想问题

| 术语 | 人话解释 | 项目位置 | 用到它的篇章 |
| --- | --- | --- | --- |
| Evidence（证据） | 一条被授权导入、带来源和编号的原始材料。系统的「事实底稿」。 | `backend/app/models/evidence.py` | [00-2](00-foundations/00-2-prompt-and-evidence.md) · [02](02-data-model.md) |
| 画像（ProfileItem） | 从证据里抽出来的结构化条目，如「技能：Python」，并且记着支撑它的证据 ID。 | `backend/app/models/profile.py`、`backend/app/profile/` | [00-4](00-foundations/00-4-data-model-in-plain-words.md) · [02](02-data-model.md) |
| 证据可追溯 | 任何结论都能点回到具体的 evidence_id；找不到依据就写「证据不足」。这是全项目的第一原则。 | `backend/app/services/jobs.py` | [00-1](00-foundations/00-1-what-is-agent.md) · [04](04-retrieval-agent.md) |
| Agent（智能体） | 能在给定范围内自己拆步骤、调用工具去办事的程序；和「固定流程」相对，也不保证每次都做对。 | `backend/app/graph/career.py` | [00-1](00-foundations/00-1-what-is-agent.md) |
| 提示词（Prompt） | 给模型的任务说明，写清目标、给什么材料、要什么输出。流畅不等于可靠。 | `backend/app/llm/`、`backend/app/profile/llm_extractor.py` | [00-2](00-foundations/00-2-prompt-and-evidence.md) |

## 检索层：怎么从一堆材料里找证据

| 术语 | 人话解释 | 项目位置 | 用到它的篇章 |
| --- | --- | --- | --- |
| RAG | 检索增强生成：先从材料里检索相关证据，再让模型基于证据回答，而不是凭空说。 | `backend/app/services/knowledge.py` | [00-3](00-foundations/00-3-rag-and-vector.md) · [04](04-retrieval-agent.md) |
| 向量 / Embedding | 把一段文字变成一组数字（坐标），意思接近的文字坐标也接近，于是能按「意思」而非字面找材料。 | `backend/app/retrieval/` | [00-3](00-foundations/00-3-rag-and-vector.md) |
| Dense + Sparse | 两路检索：Dense 按语义（意思接近），Sparse 按关键词（字面命中）。 | `backend/app/retrieval/providers.py` | [04](04-retrieval-agent.md) |
| RRF | 把两路检索的榜单合并成一个排名的规则（Reciprocal Rank Fusion）。 | `backend/app/retrieval/` | [04](04-retrieval-agent.md) |
| 重排（Reranker） | 粗排选出一批候选后，再精挑一次，把最相关的放前面。项目用粗排 Top15 → 精排 Top5。 | `backend/app/retrieval/providers.py`（`CascadingReranker`） | [04](04-retrieval-agent.md) |
| 检索模式 | 提问时可选 `rag`（证据）/ `wiki`（整理过的主题页）/ `hybrid`（两者混合），切换不用重建索引。 | `backend/app/services/knowledge.py` | [04](04-retrieval-agent.md) · [05](05-wiki.md) |
| Qdrant | 存向量的检索库。它是 Evidence 的**可重建索引**，业务数据仍以 PostgreSQL 为准。 | `docker-compose.yml`（qdrant 服务） | [01](01-quickstart.md) · [07](07-integration.md) |

## 知识组织层：把证据整理成可引用的页

| 术语 | 人话解释 | 项目位置 | 用到它的篇章 |
| --- | --- | --- | --- |
| Wiki 页 / 修订 | 把散落证据整理成一页带引用的主题说明；每次改动留一个版本，回滚是一次普通编辑而非删除历史。 | `backend/app/models/wiki.py`、`backend/app/services/wiki_pages.py` | [05](05-wiki.md) |
| 短句柄 `c000` | 编译 Wiki 时给模型看的临时引用代号；落库前会解析回稳定的 evidence_id，认不出的直接丢弃。 | `backend/app/wiki/handles.py` | [05](05-wiki.md) |
| 表格行守卫 | 防止编译过程中表格行丢失或被改动的校验；行 identity 变化时拒绝写入。 | `backend/app/wiki/tables.py` | [05](05-wiki.md) |

## 运行时层：长任务怎么可靠地跑完

| 术语 | 人话解释 | 项目位置 | 用到它的篇章 |
| --- | --- | --- | --- |
| Run / Step / Event | 一次长任务、它的步骤、以及有序进度事件。事件序号用于断线续看。 | `backend/app/models/run.py`、`backend/app/runtime/` | [06](06-runtime.md) · [01](01-quickstart.md) |
| Worker | 独立进程，从数据库里领任务来跑。**后台任务必须启动 Worker 才会执行。** | `backend/app/runtime/worker.py` | [06](06-runtime.md) |
| 幂等键（Idempotency-Key） | 同一个逻辑动作重复提交，返回同一个任务，不会重复执行或重复计费。 | `backend/app/runtime/store.py` | [06](06-runtime.md) |
| 租约（lease） | Worker 领取任务时拿到的「临时占有权」，超时未续租可被别的 Worker 收回。 | `backend/app/runtime/` | [06](06-runtime.md) |
| fencing 代次（generation） | 每次领取、取消、中断都会递增的编号；提交前校验，防止过期的旧 Worker 回调污染新状态。 | `backend/app/models/run.py` | [06](06-runtime.md) |
| SSE | Server-Sent Events，服务端把进度一条条推给浏览器；刷新后凭事件序号接着看。 | `backend/app/api/routes/runs.py`、`frontend/lib/run-events.ts` | [06](06-runtime.md) |
| outbox | 「先记账后办事」的补偿表：业务提交时先记一条待办，再异步同步到 Qdrant，失败可重放。 | `backend/app/runtime/index_outbox.py` | [06](06-runtime.md) |
| 质量门禁 | 用冻结的合成评测集做持续回归检查；分数只说明默认链路是否稳定，不代表生产准确率。 | `eval/`、`backend/app/evaluation/` | [08-2](08-advanced/08-2-evaluation.md) |

## 隐私与安全层：数据怎么收得回来

| 术语 | 人话解释 | 项目位置 | 用到它的篇章 |
| --- | --- | --- | --- |
| 用户隔离 | 检索和接口都按 `user_id` 过滤，一个用户看不到另一个用户的数据。 | `backend/app/security/`、`backend/app/services/` | [07](07-integration.md) |
| Scope Token | 限制调用方能读还是能写的令牌。 | `backend/app/security/auth.py` | [07](07-integration.md) |
| preference_signal | 「点赞 / 收藏 / 关注」这类互动记录的标记：只算兴趣线索，**不写入技能或经历**。 | `backend/app/connectors/browser_capture.py`、`backend/app/profile/extractor.py` | [阶段 5 对照实验](../README.md) · [FAQ](FAQ.md#模型与数据) |
| 数据导出 / 账号清理 | 导出自己的数据副本；永久删除会同时清理数据库、向量、对话状态与令牌，只留不含原文的审计记录。 | `backend/app/services/privacy.py` | [FAQ](FAQ.md#模型与数据) · [07](07-integration.md) |

> [!NOTE]
> 表中指向尚未发布篇章的链接会随内容补齐逐步生效；在此之前可从[教程总览](README.md)查看当前进度。

## 下一步

- 回到[开始页](START-HERE.md)选学习路线。
- 术语记不住没关系，边做边查；[常见问题](FAQ.md)按症状排好序了。
