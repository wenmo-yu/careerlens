# 数据接入、MCP 与安全边界

CareerLens 只应处理用户主动提交或明确授权导出的个人内容。服务端 Connector 是**导入器**，不是第三方平台登录或账号同步服务。另有一个可选的[本地浏览器页面采集工具](../browser-helper/README.md)：用户自己登录并点击采集当前已加载的页面条目，扩展不读取、上传或持久化 Cookie。采集清单暂存在浏览器扩展的会话内存中；导出后还需在工作台逐条核对并确认入库。

## 接入渠道

以 `GET /api/v1/connectors/registry` 为统一入口，注册表按真实能力标注来源，不把“需要平台授权”写成已实现：

| 渠道 | 已支持的输入 | 处理方式与限制 |
| --- | --- | --- |
| 文本与文件 | 自述、TXT / Markdown、PDF / DOCX、XLSX、CSV / TSV、用户另存 HTML、导出 ZIP | 解析后分块成 Evidence 并保留来源定位；旧 `.doc` 需转换，扫描页标为待 OCR；XLSX 由标准库解析 |
| 平台导出文件 | Bilibili JSON；微博 JSON / CSV | 识别外部 ID、清理简单 HTML、按 ID 或稳定指纹去重；用户主动提供 |
| 浏览器当前页采集 | Bilibili、微博、抖音、掘金、CSDN、知乎、小红书、GitHub 的可见发布与互动 | 单次读取最多 100 条、分组最多 200 条，后端单文件最多 200 条且 2 MB；不保证完整历史，互动仅作兴趣线索 |
| 公开链接证据卡 | 用户手填 URL、标题和说明 | 后端不访问链接、不证明账号归属；带 query token 的链接会被清理 |
| GitHub 仓库 | 用户自备的 fine-grained 只读令牌 | 只读仓库元数据与 README（最多 10 个仓库、单个 6000 字符）；令牌只在单次请求内存中使用，不写数据库/日志/证据；不读 issues、PR、提交。步骤见 [GitHub 仓库导入](github-token-import.md) |
| 多模态 | 图片 OCR、音视频 ASR | PaddleOCR / Faster-Whisper 为可选依赖；模型下载、格式兼容与效果需独立验收 |

示例格式、上传路由和可选依赖安装见 [API 与配置](api-and-configuration.md)。原始平台内容可能涉及他人隐私。公开作品演示请使用虚构或已脱敏内容，不要把 `.env`、数据库、真实简历或未经授权的导出文件提交到 GitHub。

## MCP 暴露什么

[`mcp/server.py`](../backend/app/mcp/server.py) 与 HTTP API 共用业务服务，因此 MCP 不维护第二套画像或分析逻辑。

| 类型 | 内容 |
| --- | --- |
| Tools | `list_user_content`、`get_evidence`、`import_text_evidence`、`search_evidence`、`get_user_profile`、`list_job_analyses`、`analyze_job_description`、`generate_career_report`、`list_career_reports`、`get_career_report` |
| Resources | `profile://{user_id}`、`evidence://{user_id}/{evidence_id}`、`report://{user_id}/{report_id}` |
| Prompts | 画像证据解释、JD 匹配复核、面试表达准备 |

本地 `stdio` 适合可信桌面客户端启动子进程；`streamable-http` 适合独立服务。后者使用 Bearer Token，对请求中的 `user_id` 与 Token subject 做校验。读操作需要 `read`，写操作需要 `write`；`manage` 可覆盖对应 Scope。MCP Tool 调用记审计事件。不要把无鉴权的 stdio 进程暴露为公共服务。

## API 权限模型

[`security/auth.py`](../backend/app/security/auth.py) 支持三种模式：

- `disabled`：默认本地演示，不要求 Token；**不适合公网**。
- `optional`：兼容旧客户端；没有 Token 的请求仍可进入，因此同样不能作为真正的公网保护。
- `required`：个人数据接口要求 Bearer Token；部署时还要设置随机 `AUTH_TOKEN_PEPPER` 与注册密钥。

Token 只在创建时返回明文，数据库存加 pepper 的哈希。Scope 为 `read`、`write`、`export`、`delete`、`manage`；具体路由会校验资源所属用户与所需 Scope。评测与观测接口是实例级能力（不归属单个用户），在 `required` 模式下要求 `manage` Scope；`disabled` 与无 Token 的 `optional` 模式放行。生产 Compose 有鉴权与密钥检查，但**没有自动提供 HTTPS 反向代理**。公网部署还需 TLS、限流、数据库与 Qdrant 端口隔离、密钥轮换和备份治理。

## 导出、删除与审计

`GET /api/v1/privacy/{user_id}/export` 获取用户数据副本；`DELETE /api/v1/evidence/{evidence_id}` 清理单条证据及其引用；`DELETE /api/v1/privacy/{user_id}` 执行账号清理并生成匿名回执，清理范围包含对话线程及其全部 `ConversationMessage` 消息。审计记录不应包含 Evidence 原文、Prompt 或 API Key。模型调用观测也仅记录模型、耗时、Token、状态等元数据。

这些接口描述的是应用数据库、索引与 checkpoint 的行为，不自动涵盖外部模型提供商的留存政策、操作系统日志、备份副本或已经下载的报告。部署方需要依据实际环境制定数据保留、备份删除传播和故障补偿策略；应用接口本身不是端到端合规承诺。
