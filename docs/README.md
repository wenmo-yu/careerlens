# CareerLens 技术文档

本目录是 [项目首页](../README.md) 的延伸：README 用于快速理解和启动项目，这里说明系统如何运行、各组件如何协作，以及测试结果的适用范围。文档以当前仓库实现为准。

| 文档 | 主要内容 |
| --- | --- |
| [界面展示](showcase.md) | 首页、案例、系统设计、工作台及业务结果的页面截图 |
| [系统架构](architecture.md) | 服务分层、请求链路、数据边界与设计取舍 |
| [数据与证据生命周期](data-and-evidence.md) | Evidence、画像、JD 分析和报告的关联、更新与删除 |
| [两期验收与 Wiki 使用](phase-1-2-validation.md) | A–D 验收、工作台操作、迁移与配置 |
| [第三期后台任务与恢复](phase-3-runtime.md) | Worker、Run/Step/Event、审批、取消、重放、索引补偿与多 Agent |
| [评分与学习路线](job-matching-and-planning.md) | 权重、算例、排期和历史分析失效机制 |
| [Agent、检索与模型](agent-and-retrieval.md) | LangGraph 工作流、混合检索、模型切换与降级 |
| [接入、MCP 与安全](integrations-and-security.md) | 数据导入、MCP 接口、用户隔离与权限 |
| [评测与运维](evaluation-and-operations.md) | 评测口径、本地验收和故障定位 |
| [API 与配置参考](api-and-configuration.md) | 完整接口清单、非 Docker 启动、迁移、真实模型与生产配置 |

- **零基础入门**：从[教程开始页](../tutorials/从这里开始.md)进入——10 分钟零安装做完第一道证据判断题，再按基础选路线。
- **想快速上手**：先看[项目首页](../README.md)的 Quick Start；想本机跑通，走[第 01 篇](../tutorials/01-第一次跑起来.md)。
- **想理解设计**：按"[架构](architecture.md) → [数据模型](data-and-evidence.md) → [Agent 与检索](agent-and-retrieval.md) → [评测](evaluation-and-operations.md)"阅读。
- **想动手复刻**：走[实现教程](../tutorials/README.md)，按依赖顺序逐层实现。查词用[术语表](../tutorials/术语表.md)，卡住看[常见问题](../tutorials/常见问题.md)。
- **集成外部客户端**：参阅[接入、MCP 与安全](integrations-and-security.md)；完整接口见[API 与配置](api-and-configuration.md)。

## 运行与验证范围

- 基础 Compose 已完成 Web → FastAPI → PostgreSQL/Qdrant → 画像 → JD 分析 → 报告 → 对话闭环验证；CI 的 `docker-smoke` 以双 Worker 覆盖后台 run 幂等、SSE 续看、Wiki 审批与取消、模式切换。
- 自动化测试当前 **158 项后端用例全绿**，前端通过 ESLint、TypeScript 类型检查与生产构建；验收口径见[第三期说明](phase-3-runtime.md)与 [Quality Gate](https://github.com/wenmo-yu/careerlens/actions/workflows/quality.yml)。
- 数据接入支持 PDF / DOCX / XLSX / TXT / Markdown；XLSX 由标准库解析，无需 openpyxl。扫描 PDF 页标记为待 OCR，不伪造文本。
- DeepSeek/OpenAI-compatible、本地 Qwen、PaddleOCR/Faster-Whisper 与可观测性属于可配置集成；真实模型质量需按[路线图](../ROADMAP.md)在授权或合成样本上单独验收，不把开发集分数当成真实准确率。
- 公网部署与本地运行具有不同的安全边界，详见[安全说明](integrations-and-security.md)。

如果文档与代码不一致，以代码和实际运行结果为准，并欢迎通过 Issue/PR 指出具体差异。
