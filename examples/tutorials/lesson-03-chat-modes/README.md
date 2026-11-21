# 练习 03 · 三种检索模式

**对应课程**：[04 检索 Agent](../../../tutorials/04-retrieval-agent.md)
**核对什么**：同一问题切 rag / wiki / hybrid，看诊断与引用来源。

## 运行

```bash
python3 examples/tutorials/lesson-03-chat-modes/main.py
```

脚本用 `lesson-03-chat-modes` 教学账号导入证据、重建画像，再编译一页 Wiki；不需要先在界面中操作。重跑时读取已有 Wiki 的 `version` 作为 `base_version`，无需删除旧页。脚本通过证据搜索确认本次 Evidence 可检索，并不把 Wiki 列表当成索引就绪检查。

## 预期输出

```text
[rag] backend=qdrant rag_count=1 wiki_count=0 source_kinds=['rag']
[wiki] backend=- rag_count=0 wiki_count=1 source_kinds=['wiki']
[hybrid] backend=qdrant rag_count=1 wiki_count=1 source_kinds=['rag', 'wiki']
[hybrid] knowledge_fusion=rank_interleave
OK：三种模式都命中预期来源，并能追溯到同一条原始证据。
```

具体条数取决于当前教学账号的材料。本地检索或回退时，`backend` 可为 `local`；Compose 验收要求 RAG 一侧为 `qdrant`。脚本不比对回答文本。

## 它验证了什么

- `mode` 是 `/api/v1/chat` 的**请求体字段**；
- `rag` 命中刚导入的证据 ID，`wiki` 命中编译页，且页的 `chunk_refs` 能指回同一 ID；
- 对本练习的输入，`hybrid` 必须有两类实际命中，诊断也必须与 `evidence[*].source_kind` 一致。只返回空列表或有模式名，不算通过。

## 一个诚实的细节

`wiki` 模式的 `retrieval` 里**没有** `backend` / `fusion` / `reranker` 这些键——因为它根本没走证据检索器。这不是 bug，见 [04 教程](../../../tutorials/04-retrieval-agent.md)的说明。
