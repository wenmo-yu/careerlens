# 练习 03 · 三种检索模式

**对应课程**：[04 检索 Agent](../../../tutorials/04-retrieval-agent.md)
**核对什么**：同一问题切 rag / wiki / hybrid，看诊断与引用来源。

## 运行

```bash
python3 examples/tutorials/lesson-03-chat-modes/main.py
```

脚本会自己准备证据并编译一页 Wiki（用专用教学用户），所以不需要先在界面上点。

## 预期输出

```text
[rag]    rag_count=... wiki_count=... source_kinds=['rag']
[wiki]   rag_count=... wiki_count=... source_kinds=['wiki']
[hybrid] rag_count=... wiki_count=... source_kinds=['rag', 'wiki']
[hybrid] knowledge_fusion=rank_interleave
OK：三种模式的诊断与引用来源随模式变化（回答文本不要求一致）。
```

具体条数取决于合成材料，**回答文本不要求逐字一致**；脚本只校验诊断字段的结构和关系。

## 它验证了什么

- `mode` 是 `/api/v1/chat` 的**请求体字段**；
- 诊断在返回的 `retrieval` 里，引用的来源类型在顶层 `evidence[*].source_kind`；
- `hybrid` 会同时有 rag 和 wiki 两类命中，诊断里出现 `knowledge_fusion: "rank_interleave"`。

## 一个诚实的细节

`wiki` 模式的 `retrieval` 里**没有** `backend` / `fusion` / `reranker` 这些键——因为它根本没走证据检索器。这不是 bug，见 [04 教程](../../../tutorials/04-retrieval-agent.md)的说明。
