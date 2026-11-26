# CareerLens 界面展示

下面的页面截取自本地 Docker 运行的 CareerLens。案例中的人物、经历与岗位均为虚构内容；工作台结果使用默认确定性 Demo Provider，展示的是业务流程与证据链，不代表真实模型效果。返回[项目首页](../README.md)。

## 页面导航

| 页面 | 设计重点 | 本地地址 |
| --- | --- | --- |
| 产品首页 | 项目定位、能力亮点、端到端流程 | `http://localhost:3000/` |
| 案例体验 | 沿着一个虚构人物的经历理解完整链路 | `http://localhost:3000/demo` |
| 系统设计 | 分层、证据生命周期、Agent 与安全边界 | `http://localhost:3000/architecture` |
| 快速开始 | 启动命令、服务入口和模型切换说明 | `http://localhost:3000/start` |
| 交互工作台 | 实际调用 API 的画像、匹配、报告与 Copilot | `http://localhost:3000/workspace` |

## 1. 产品首页

首页用证据驱动的职业判断作为主线。标题下方内嵌工作台的真实渲染截图，数据明确标注为虚构示例；它不是已登录用户的资料，完整交互看下一节。

![CareerLens 新版产品首页](assets/overview.jpg)

## 2. 虚构案例体验

案例页是帮助理解流程的静态内容。第一张截图只展示上半部的案例入口与两份虚构输入（自述 + 目标 JD）；逐项要求和缺口见第二张局部图。完整操作请进入工作台。

![案例页上半部：入口与两份虚构输入](assets/demo.jpg)

![案例页岗位要求表：Kubernetes 为 gap，其余多为 partial，保留可见缺口供观察题引用](assets/demo-requirements.jpg)

## 3. 系统设计

系统设计页顶部用四层概览说明交互层、服务层、决策层与数据层的职责；JD 匹配与 Copilot 检索两条请求链、Run/Worker 和权限边界见页面下半部及[架构文档](architecture.md)。

![系统设计页顶部：交互层 / 服务层 / 决策层 / 数据层四层概览](assets/architecture.jpg)

## 4. 快速开始与工作台

快速开始页顶部给出 Docker 启动与验收命令，服务入口与三种生成模型模式在下半页。工作台保留真实业务接口，预填虚构内容，无需 API Key 即可走默认 Demo 模式。

![快速开始页顶部：Docker 启动与验收命令](assets/start.jpg)

![工作台总览：预填的导入、画像、岗位、报告与 Copilot 区域](assets/workspace.jpg)

> **待补截图**：上传 HTML → 后台任务已完成 → 打开结果 → 导入结果卡（可读证据、重复数、待 OCR、文件名）。可复现路径见[端到端用例](../frontend/e2e/happy-path.spec.ts)。

## 5. 构建职业画像

导入虚构自述后，系统将其转为 Evidence，并提取结构化画像条目。图中四块内容分别是类别分布（按类别数量）、证据覆盖度（要结合有效证据条数看）、L1–L5 技能矩阵与证据时间线。技能用五格刻度、可信度高/中/低和证据条数表示——单条自述通常只有 `L2 / 1 条证据 / 可信低`，不会画成“掌握度 100%”。时间线已能看到原文片段；不是每块都有“查看文字表格”按钮。

![画像概览：类别分布、证据覆盖度、L1–L5 技能矩阵与证据时间线](assets/profile.jpg)

> **待补截图**：展开某条技能（如 Python）的证据卡，示范从画像条目回查原文。

## 6. 岗位逐项匹配

从 JD 识别要求，与当前画像逐项对照：有证据但只够部分支撑的标 `partial`，没有证据的标 `gap`，右栏按缺口、现有等级与每周可投入时间排出学习路径。这张局部图没有拍到分数卡；匹配分的例子见下一节报告截图，**它不是录用概率**。

![逐项匹配结果与 Gap 学习路径：partial / gap、证据条数与按周计划](assets/job-match.jpg)

> **待补截图**：匹配分数卡与分数拆解；学习看板状态与课程目录（先修、学时、验收方式）；两份 JD 的对比响应或并列分析结果。

## 7. 版本化职业报告

画像与岗位分析可固化为独立报告版本，并下载 Markdown。截图显示 v9 的摘要四项（画像、方向、缺口、行动）与可展开的八个结构化章节，本例为 `demo / deterministic`、1 条 Evidence；匹配分 56.9% 是规则分，不是录用概率。

![报告 v9：摘要四项与可展开的结构化章节（demo / deterministic，1 条 Evidence）](assets/report.jpg)

> **待补截图**：报告中“证据目录”的展开状态。

## 8. Career Copilot 与证据引用

对话区展示回答、可点开的引用来源 chip 与检索诊断（`local` / `retrieval fallback` / `model fallback`）；本次为确定性回答，不应描述为真实大模型生成效果。截图里的原文尚未展开。

![Copilot 回答卡：RAG 来源 chip 与检索诊断（local / retrieval fallback / model fallback）](assets/copilot.jpg)

> **待补截图**：点击引用后展开的原始 Evidence。

## 9. 可选模块：自我探索与数据控制（待补截图）

主流程之外，工作台还提供自陈测评与数据控制入口。自陈结果单独保存，不进入事实画像、不改匹配分；数据控制展示导出路径与审计列表。两处资料均为合成示例。

- 量表、计分与许可边界见[测评题库与许可](assessments.md)。
- 导入来源、权限与审计边界见[接入、MCP 与安全](integrations-and-security.md)。
- GitHub 只读令牌见[GitHub 仓库导入](github-token-import.md)。

> **待补截图**：一份合成测评结果，以及导出路径 / 审计列表。

每条结果的实现边界见[架构说明](architecture.md)和[Agent、检索与模型](agent-and-retrieval.md)。
