# CareerLens 技术文档

本目录是 [项目首页](../README.md) 的延伸：README 用于快速理解和启动项目，这里按问题说明系统如何运行、各组件如何协作，以及测试结果的适用范围。文档以当前仓库实现为准。

| 文档 | 主要内容 |
| --- | --- |
| [界面展示](showcase.md) | 首页、案例、系统设计、工作台及业务结果的页面截图与图注 |
| [系统架构](architecture.md) | 服务分层、部署拓扑、两条请求链路、数据边界与设计取舍 |
| [数据与证据生命周期](data-and-evidence.md) | Evidence、画像、岗位分析、报告、Wiki 引用与扩展数据的关联、更新与删除 |
| [画像、推荐与自陈探索](profile-and-recommendations.md) | 导入结果卡、画像概览、职业/课程目录、多 JD 对比、学习看板、测评边界与多 Agent |
| [评分与学习路线](job-matching-and-planning.md) | 权重、算例、排期、课程目录、作品验收与历史分析失效机制 |
| [Agent、检索与模型](agent-and-retrieval.md) | LangGraph 条件路由、默认检索路径、本地回退、模型切换与降级 |
| [后台任务与恢复（第三期）](phase-3-runtime.md) | Worker、Run/Step/Event、审批、取消、重放、索引补偿与多 Agent |
| [接入、MCP 与安全](integrations-and-security.md) | 来源注册表、浏览器采集、公开链接卡、GitHub 令牌、MCP 接口与权限 |
| [Wiki 与早期验收](phase-1-2-validation.md) | A–D 验收、Wiki 编译与版本、工作台操作、迁移与配置 |
| [测评题库与许可](assessments.md) | 三份自写量表的题目来源、许可比对、计分规则、结果边界与新增量表流程 |
| [GitHub 仓库导入](github-token-import.md) | 自备只读令牌的做法、读取范围、令牌不落库的约束与故障排查 |
| [评测与运维](evaluation-and-operations.md) | 评测口径、本地验收、监控指标和故障定位 |
| [API 与配置参考](api-and-configuration.md) | 按任务组织的接口速查、非 Docker 启动、迁移、真实模型与生产配置 |

- **零基础入门**：从[教程开始页](../tutorials/从这里开始.md)进入——3 分钟零安装做完第一道证据判断题，再按基础选路线。
- **想快速上手**：先看[项目首页](../README.md)的 Quick Start；想本机跑通，走[第 01 篇](../tutorials/01-第一次跑起来.md)。
- **想理解设计**：按"[架构](architecture.md) → [数据与证据](data-and-evidence.md) → [Agent 与检索](agent-and-retrieval.md) → [后台任务](phase-3-runtime.md) → [评测](evaluation-and-operations.md)"阅读。
- **想动手复刻**：走[实现教程](../tutorials/README.md)，按依赖顺序逐层实现。查词用[术语表](../tutorials/术语表.md)，卡住看[常见问题](../tutorials/常见问题.md)。
- **集成外部客户端**：参阅[接入、MCP 与安全](integrations-and-security.md)；接口入口见[API 与配置参考](api-and-configuration.md)，完整参数以 Swagger 为准。
- **想看新增功能**：自陈测评与 MBTI 边界见[测评题库与许可](assessments.md)；GitHub 只读令牌见[GitHub 仓库导入](github-token-import.md)；画像模式、课程目录、多 JD 对比与学习看板见[画像、推荐与自陈探索](profile-and-recommendations.md)；所有页面截图见[界面展示](showcase.md)。

## 运行与验证范围

- 基础 Compose 已完成 Web → FastAPI → PostgreSQL/Qdrant → 画像 → JD 分析 → 报告 → 对话闭环验证；CI 的 `docker-smoke` 以双 Worker 覆盖后台 run 幂等、SSE 续看、Wiki 审批与取消、模式切换。
- 自动化测试当前 **246 项后端用例全绿**（覆盖率门槛 78%，实测约 82%）；前端通过 ESLint、TypeScript 类型检查、Node 单测与生产构建；Playwright 5 项端到端覆盖导入、文档上传、画像、岗位匹配、报告、空状态与 404。口径见[Quality Gate](https://github.com/wenmo-yu/careerlens/actions/workflows/quality.yml)与[第三期说明](phase-3-runtime.md)。
- 数据接入支持自述粘贴，PDF / DOCX / XLSX / CSV / TSV / TXT / Markdown，用户另存 HTML 与导出 ZIP，图片 OCR / 音视频 ASR，公开链接证据卡、GitHub 只读令牌，以及八个平台的当前页采集。XLSX 由标准库解析，无需 openpyxl；旧 `.doc` 需转换，扫描 PDF 页标为待 OCR，互动只作兴趣线索。
- DeepSeek/OpenAI-compatible、本地 Qwen、PaddleOCR/Faster-Whisper 与可观测性属于可配置集成；真实模型质量需按[路线图](../ROADMAP.md)在授权或合成样本上单独验收，不把开发集分数当成真实准确率。
- 公网部署与本地运行具有不同的安全边界，详见[接入、MCP 与安全](integrations-and-security.md)。

如果文档与代码不一致，以代码和实际运行结果为准，并欢迎通过 Issue/PR 指出具体差异。
