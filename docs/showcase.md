# CareerLens 界面展示

以下图片截取自本地 Docker 运行的 Web 工作台，使用同一组虚构经历与岗位描述。生成模型为默认确定性 Demo Provider；它展示业务流程与证据引用方式，不代表真实模型效果。返回[项目首页](../README.md)。

## 1. 构建职业画像

导入自述后，系统将其转为 Evidence，并提取带证据数量和置信度的结构化画像条目。

![由虚构经历生成的结构化职业画像](assets/profile.jpg)

## 2. 岗位逐项匹配

从 JD 识别要求，与当前画像逐项对照，显示 `partial`、`gap` 和学习路径。截图中的 56.9% 是该规则模型下的可验证匹配分数，**不是录用概率**。

![JD 要求、匹配分数和能力缺口](assets/job-match.jpg)

## 3. 版本化职业报告

画像与岗位分析可固化为独立报告版本，并下载 Markdown。截图显示由 Demo Provider 生成的确定性版本。

![包含画像、方向、缺口和行动建议的职业报告](assets/report.jpg)

## 4. Career Copilot 与证据引用

对话区展示回答、实际检索后端与展开的原始 Evidence。截图标注 `MODEL FALLBACK`，表示本次使用的是默认确定性回答，不应将其描述成真实大模型生成效果。

![Career Copilot 回答及展开的 Evidence 引用](assets/copilot.jpg)

系统架构与每条结果的实现边界见[架构说明](architecture.md)和[Agent、检索与模型](agent-and-retrieval.md)。
