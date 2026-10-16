# CareerLens 技术文档

本目录是 [项目首页](../README.md) 的延伸：README 用于快速理解和启动项目，这里说明系统如何运行、各组件如何协作，以及测试结果的适用范围。文档以当前仓库实现为准。

| 文档 | 主要内容 |
| --- | --- |
| [界面展示](showcase.md) | 职业画像、岗位分析、报告和对话的实际运行截图 |
| [系统架构](architecture.md) | 服务分层、请求链路、数据边界与设计取舍 |
| [数据与证据生命周期](data-and-evidence.md) | Evidence、画像、JD 分析和报告的关联、更新与删除 |
| [Agent、检索与模型](agent-and-retrieval.md) | LangGraph 工作流、混合检索、模型切换与降级 |
| [接入、MCP 与安全](integrations-and-security.md) | 数据导入、MCP 接口、用户隔离与权限 |
| [评测与运维](evaluation-and-operations.md) | 评测口径、本地验收和故障定位 |

建议从[项目首页](../README.md)了解功能和启动方法，再按“[架构](architecture.md) → [数据模型](data-and-evidence.md) → [Agent 与检索](agent-and-retrieval.md) → [评测](evaluation-and-operations.md)”阅读实现细节；集成外部客户端时参阅[接入、MCP 与安全](integrations-and-security.md)。

## 运行与验证范围

- 基础 Compose 已在本机完成 Web → FastAPI → PostgreSQL/Qdrant → 画像 → JD 分析 → 报告 → 对话闭环验证，同时覆盖 MCP 鉴权、后端测试和前端静态检查。
- DeepSeek/OpenAI-compatible、本地 Qwen、PaddleOCR/Faster-Whisper 与可观测性属于可配置集成；实际效果取决于所用模型、密钥、硬件和数据。
- 合成评测用于代码回归，不等同真实用户场景准确率。公网部署与本地运行具有不同的安全边界，详见[安全说明](integrations-and-security.md)。

如果文档与代码不一致，以代码和实际运行结果为准，并欢迎通过 Issue/PR 指出具体差异。
