# 00-5 · LangGraph 与工作流：把「下一步」画成一张图

**只用浏览器。** 阅读约 14–16 分钟，跟做约 10 分钟。学完你能从一次提问里指出状态、节点、条件边、停止点，并说清 checkpointer 和消息历史不是同一回事。

## 同一句话，为什么会走两条完全不同的路

对 CareerLens 说「为什么认为我会 Python？」，系统会检索证据再组织回答。说「记住我更希望做后端」，它不会偷偷改长期画像，而是提示你去专门的草案确认界面。两句话都进了同一个聊天框，处理路径却不同。

差别不是模型突然更懂事，而是应用在运行前就写好了一个判断：**先看问题意图，再决定去哪儿。** 这类「共享状态 + 节点 + 边」的编排，就是 LangGraph 解决的事。官方文档称它是「用于长时间运行、有状态 Agent 的低层编排框架与运行时」，强调可在同一张图里混用确定性步骤和模型驱动步骤。 [LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)

## 一张图只有三个基本零件

| 零件 | 官方定义 | 课堂里的说法 | CareerLens 里去看什么 |
| --- | --- | --- | --- |
| State（状态） | 应用状态的共享快照，通常是带类型的 schema | 当前任务带着走的记事本 | `CareerState`，见 `backend/app/graph/career.py` |
| Node（节点） | 读取状态、做工作、返回更新的函数 | 一个明确的工作步骤 | `understand_intent`、`retrieve_evidence` 等五个节点 |
| Edge（边） | 固定或条件的转移，决定下一个节点 | 下一步走哪条路 | `START` 入口、`route_intent`、`route_answer`、`END` |

图要先**编译**再运行；编译时可以挂上 checkpointer 等运行选项。节点可以是普通 Python 函数，也可以调用模型。文档特别指出，节点是检查点和重试边界——这解释了为什么「要不要单独做一个节点」要看它是否会改变后续路径，而不是看它代码长不长。 [Graph API 说明](https://docs.langchain.com/oss/python/langgraph/graph-api)

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"system-ui, sans-serif","fontSize":"14px","lineColor":"#55746c","edgeLabelBackground":"#f4f8f6"},"flowchart":{"nodeSpacing":22,"rankSpacing":26,"curve":"basis"}}}%%
flowchart TB
    accTitle: CareerLens 对话图的有限分支
    accDescr: 先理解意图；画像修正走确认指引，其余走检索；检索后再按是否有岗位分析分到缺口答复或普通答复。
    S(["START · 一条问题"]) --> I["understand_intent"]
    I -->|memory_update| H["memory_guidance · 提示草案确认"]
    I -->|其他意图| R["retrieve_evidence · 限定用户检索"]
    R -->|有岗位分析且问缺口| G["compose_gap_answer"]
    R -->|其他| A["compose_answer"]
    H --> E1(["END"])
    G --> E2(["END"])
    A --> E3(["END"])
    style I fill:#fff4d9,stroke:#ba893b,color:#644117
    style R fill:#eaf6f1,stroke:#60a28d,color:#143f36
    style H fill:#f4f1ec,stroke:#a18b71,color:#5a4939
```

图里的每个箭头都有触发条件。`route_intent` 只看意图是不是 `memory_update`；`route_answer` 只在「技能缺口问题 + 已有岗位分析」同时成立时走缺口答复。其余都走普通答复。**有限分支**让路径可以在浏览器练习里被一条条点出来，也是它和「模型自己决定调哪个工具」的循环最大的区别。

## 状态怎么被改写

CareerLens 的 `CareerState` 声明了问题、用户、历史、意图、画像、证据、检索诊断、答复、模型诊断、岗位分析、模式等字段。节点只返回自己改的部分：

- `understand_intent` 返回意图，并把检索结果和诊断清空，避免上一轮残留混进这一轮。
- `retrieve_evidence` 返回 `retrieved_evidence` 和 `retrieval_diagnostics`，不改答复字段。
- `compose_answer` 返回答复与模型诊断；失败时 `fallback: true` 并记下原因。

LangGraph 默认用「后写覆盖」合并同一字段；需要累积的字段可以定义 reducer，例如把多次工具结果追加成列表。多数时候不必自己写 reducer：一个节点返回部分更新，比把整个状态复制一遍更不容易出错。 [状态与 reducer 官方说明](https://docs.langchain.com/oss/python/langgraph/graph-api)

### 节点里的模型步骤也有护栏

`compose_answer` 先准备一份确定性回答。只有配置了真实模型，才把问题、意图、画像、检索证据和最近 12 条历史打包成结构化输入。输出必须是 JSON，且只能引用本次检索返回的 ID；超时、非法 JSON 或未知引用都会回退。 [回复节点源码](../../backend/app/graph/career.py) · [00-2 的三关检查](00-2-提示词与证据.md)

这说明 LangGraph 不负责「让模型变诚实」。它负责让步骤可执行、可观察、可停止；证据边界仍由应用自己的提示词、校验和回退规则实现。

## 续跑靠什么：checkpointer 与 thread

官方文档把持久化分两类：**checkpointer** 保存某个 thread 的图状态快照，用于对话连续、人工介入、时间旅行和故障恢复；**store** 保存跨 thread 的应用数据，例如长期偏好。调用图时传 `thread_id`，就知道恢复到哪份状态。 [持久化官方说明](https://docs.langchain.com/oss/python/langgraph/persistence)

CareerLens 默认用 `InMemorySaver` 编译图；配置持久化后端时，启动阶段会换成 `AsyncPostgresSaver`。进程重启后，内存版本不保留 checkpoint，数据库版本保留。 [checkpoint 配置源码](../../backend/app/graph/checkpoint.py)

容易混淆的三样东西：

| 名字 | 保存什么 | 作用域 |
| --- | --- | --- |
| checkpoint | 一次图执行到某节点的状态快照 | 一个 `thread_id` |
| 消息表 `ConversationMessage` | 用户在聊天框里看到的历史消息 | 一个会话，可回看、可组装上下文 |
| 长期画像 `ProfileItem` | 从证据抽取并经用户确认的能力条目 | 一个用户，跨会话 |

它们不是同一份数据。对话续接主要靠消息表提供上下文；checkpoint 管图的运行状态；画像的长期修改走「草案 → 确认」接口，不由图在聊天里自动提交。 [系统设计文档](../../docs/agent-and-retrieval.md)

### 人工介入不一定是图的 interrupt

LangGraph 官方的人类介入机制是在节点里调用 `interrupt()` 暂停，由 checkpointer 保存状态，调用方用同一个 `thread_id` 和 `Command(resume=...)` 恢复；可用于审批、审阅编辑和工具调用确认。 [人类介入官方说明](https://docs.langchain.com/oss/python/langgraph/interrupts)

CareerLens 当前**没有在对话图里用 `interrupt()` 暂停**。它用的是独立 API：先生成画像变更草案，用户在界面上确认或拒绝。效果同样是「机器不替人写入」，但实现在不同层。不要看到「确认」就以为图里一定有 interrupt。

## 跟做：在纸上追三条路径

不用安装任何东西。回答下面三问，再用源码或练习页核对。

| 输入 | 先写路径 | 再写出该节点返回的状态字段 |
| --- | --- | --- |
| 「为什么认为我会 Python？」 | START → ? → ? → ? → END | 意图、检索候选、诊断、答复 |
| 「还差什么？」且已有岗位分析 | 哪一步开始和上一题不同？ | 答复来自已存分析还是模型 |
| 「记住我更希望做后端」 | 为什么没有检索就结束？ | 会写入长期画像吗？ |

<details>
<summary>核对路径</summary>

第一题走 `understand_intent → retrieve_evidence → compose_answer → END`，意图是 `evidence_explanation`，检索带诊断，回答校验引用。第二题在 `route_answer` 改道到 `compose_gap_answer`，读取已有的 `JobAnalysis`，不重新让模型编岗位结论。第三题在 `route_intent` 改道到 `memory_guidance`，只提示去草案确认界面，不写长期画像。

三题都没出现循环。CareerLens 的对话图是有限状态工作流，不是「想查几轮就查几轮」的自主研究 Agent。

</details>

**换一题。** 设想一个报销助手：读票据、查制度、缺附件时请人补、最后写结论。先画出节点和条件边，再指出哪个节点应该成为检查点。你会发现关键不是节点数，而是哪里需要停下来等人和哪里失败后要重来。

## 什么时候值得用 LangGraph

- 同一个流程里有固定规则步骤和模型步骤，且要混着走。
- 下一步依赖上一步状态，需要分支、循环或等待人工确认。
- 运行可能跨请求、需要续接或失败恢复。

如果只做一次「把自述改专业」的调用，一个函数就够。LangGraph 也不会自动带来证据校验、权限隔离或正确的提示词——那些仍是应用代码的责任。 [LangChain 产品分层说明](https://docs.langchain.com/oss/python/concepts/products)

## 下一步

你已经能用「状态 / 节点 / 边 / 续跑」描述一张图。接下来补一块基础知识：去 [00-6 LangChain 入门](00-6-LangChain与模型工具.md)系统认识模型、消息、提示词模板、结构化输出、链、工具、Agent、记忆与检索组件，并看清它们和 LangGraph、和本项目的关系。
