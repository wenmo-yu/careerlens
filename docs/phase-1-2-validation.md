# 两期验收与 Wiki 使用

## 八项复核

| 任务 | 结论与验收点 |
| --- | --- |
| 1/A 解析契约 | 原先只有契约和表，上传并未写入。现在文件和媒体上传同事务保存来源、解析块和证据，隐私导出可核查关联。 |
| 1/B 多格式解析 | PDF 保存页号和位置，DOCX 保存标题/段落/表格，CSV/TSV 保留表格；OCR 框和 ASR 时间段进入实际上传链路。扫描 PDF 页以待 OCR 状态记录，不假装已识别正文。 |
| 1/C 去重 | 原文件按用户与字节哈希去重；相同块内容复用 Evidence，不同来源位置继续保留。唯一索引保护相同内容的并发写入。 |
| 1/D 数据一致性 | 报告版本唯一约束和重试、画像删除抑制及报告过期标记保留；确认纠正事务提交后才更新检索索引。 |
| 2/A Wiki 版本 | 数据库更新带版本条件；正文和引用一起快照、回滚。先清理自动修订；无来源记录的旧版本不能回滚。 |
| 2/B Wiki 编译 | 未知短句柄不会入库；无有效引用时使用确定性版本。失效或不属于当前用户的证据被拒绝；表格守卫会检查重复行。 |
| 2/C 知识检索 | 工作台支持选择证据编译专题，并切换 RAG、Wiki 或混合；混合交错合并两个排序，避免直接比较不同评分。 |
| 2/D 模型与重排 | 角色绑定使用同一 AI 供应商的不同模型；级联从整个粗排候选中选精排前列。Compose 已传递配置，默认行为不变。 |

## 工作台与 API

1. 导入证据并生成画像。在「Career Copilot」展开「从证据编译 Wiki 专题」，填写标题，加载并勾选最多 50 条证据后编译。
2. **RAG** 检索原证据；**Wiki** 检索已编译专题；**混合** 同时检索两者。切换模式不需要重建，同一对话可以继续使用。
3. 展开回答的引用即可区分原证据和 Wiki 页面。需要完整专题时点「打开 Wiki 全文」。

对应 API：`POST /api/v1/wiki/compile`、`GET /api/v1/wiki?user_id=...`、`GET /api/v1/wiki/{slug}?user_id=...`、`GET /api/v1/wiki/{slug}/revisions`、`POST /api/v1/wiki/{slug}/revert`。创建时不传 `base_version`；更新时必须传当前版本，冲突返回 `409`。对话请求 `POST /api/v1/chat` 的 `mode` 默认为 `rag`。鉴权开启时，读取和编译分别需要 `read` 和 `write` 权限。

删除单条证据会删除其解析块和受影响的 Wiki 派生内容。历史对话、已生成的报告和已导出的副本不会重写；引用该证据的报告会标记过期。需要清除账户关联的服务端数据时，使用账户删除。

## 部署和验证

- 升级已有数据库先执行 Compose 的 `migrate` 服务，或在配置好 `DATABASE_URL` 的后端环境运行 `python -m app.migration_runner`。历史上传未保留原始文件，不会自动补回解析位置；需要原始位置时重新上传。迁移保留并发产生的旧重复 ID，不强行合并已有引用。
- `MODEL_ROLE_BINDINGS=answer=model-a,wiki=model-b,analysis=model-c,profile=model-d`。未配置的角色使用 `AI_MODEL`；API 地址和密钥仍取 `AI_BASE_URL`、`AI_API_KEY`。
- `RERANK_STAGES_ENABLED=true` 可在 Qdrant 检索链路启用级联，默认粗选 15 条、精排提升前 5 条；可通过 `RERANK_COARSE_TOP_K` 和 `RERANK_FINE_TOP_K` 调整。无 Qwen 时使用词法；本地回退检索不走级联。
- 合并前以 GitHub Actions 的 **Quality Gate** 为准。后端测试覆盖结构化落库、去重、引用回滚、删除联动和并发版本；Docker 冒烟覆盖 PostgreSQL、Qdrant、文件上传与三种模式。真实 OCR/ASR 模型、扫描 PDF 自动 OCR 和实际业务检索质量不由此验收。
