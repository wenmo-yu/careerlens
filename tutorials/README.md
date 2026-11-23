# CareerLens 教程

这一系列教程带你**从零开始看明白 CareerLens，再把它跑起来、复刻出来**。零基础从[开始页](START-HERE.md)进入；只想理解原理的人，用浏览器做完第一题就能入门，不必先装软件。

> 从没写过代码？先走[从这里开始](START-HERE.md)（10 分钟，零安装）。有基础、想直接上手？跳到[第 01 篇](01-quickstart.md)。

## 学习路径

```text
开始页 START-HERE（零安装第一题 + 选路线）
        ↓
00 阶段 0：看得懂 —— Agent / 提示词与证据 / RAG / 数据模型（浏览器即可）
        ↓
01 跑通与建立心智模型
        ↓
02 数据模型：Evidence / Profile / Run 三张核心表
        ↓
03 解析层：把 PDF/DOCX/表格变成带位置的 Evidence
        ↓
04 检索 Agent：Dense+Sparse → RRF → 重排 → 可追溯回答
        ↓
05 知识组织：编译带引用的 Wiki 页与版本不变量
        ↓
06 后台运行时：Run/Step/Event、Worker、幂等与恢复
        ↓
07 组装：把模块接进 FastAPI 与 Next.js 工作台
        ↓
08 进阶：真实模型 / 评测 / 贡献
```

## 教程目录

链接只指向**已可阅读**的篇章。计划中的篇章标为「计划中」，先给出路线，不放坏链。

| 序号 | 主题 | 你将做到 | 状态 / 对应源码 |
| --- | --- | --- | --- |
| — | [从这里开始](START-HERE.md) | 零安装做完第一道证据判断题，选好学习路线 | 已发布 |
| [00-1](00-foundations/00-1-what-is-agent.md) | Agent 是什么 | 分清语言模型、固定流程与 Agent | 已发布 · 零安装 |
| [00-2](00-foundations/00-2-prompt-and-evidence.md) | 提示词与证据 | 看出「说得顺不等于说得对」 | 已发布 · 零安装 |
| [00-3](00-foundations/00-3-rag-and-vector.md) | RAG 与检索 | 分清关键词与语义检索，知道「相关 ≠ 支持」 | 已发布 · 零安装 |
| [00-4](00-foundations/00-4-data-model-in-plain-words.md) | 数据模型大白话 | 说清证据→画像→匹配→报告这条链 | 已发布 · 零安装 |
| [01](01-quickstart.md) | 从零跑通 | 本机启动闭环，走一遍数据流 | 已发布 · `docker-compose.yml`、`frontend/app/workspace` |
| [02](02-data-model.md) | 数据模型 | 理解 Evidence、ProfileItem、Run 三张表 | 已发布 · `backend/app/models/` |
| [03](03-parsing.md) | 解析层 | 结构化解析与去重、PDF/DOCX/XLSX | 已发布 · `backend/app/ingestion/` |
| [04](04-retrieval-agent.md) | 检索 Agent | 双路召回、RRF、重排、引用校验、三模式切换 | 已发布 · `backend/app/retrieval/`、`backend/app/graph/` |
| [05](05-wiki.md) | 知识组织 | Wiki 编译、短句柄引用、版本与回滚 | 已发布 · `backend/app/wiki/`、`backend/app/services/wiki_pages.py` |
| [06](06-runtime.md) | 后台运行时 | 幂等提交、租约、fencing、SSE 续看 | 已发布 · `backend/app/runtime/`、`backend/app/api/routes/runs.py` |
| [07](07-integration.md) | 接入与验证 | API、工作台、数据库、Worker、质量门禁 | 已发布 · `backend/app/api/`、`frontend/components/run-center.tsx` |
| [08-1](08-advanced/08-1-real-models.md) | 真实模型 | Demo 与真实链路、配置、收藏卡对照实验 | 已发布 · `backend/app/llm/` |
| [08-2](08-advanced/08-2-evaluation.md) | 评测 | 复跑冻结基线、四项指标口径 | 已发布 · `eval/`、`backend/app/evaluation/` |
| [08-3](08-advanced/08-3-contribute.md) | 贡献与结课 | 提交可复查 PR、结课小项目 | 已发布 · `CONTRIBUTING.md` |

## 工具书与辅助路线

- [术语表](GLOSSARY.md)——第一次遇到先解释，按层集中索引，随查不用背。
- [常见问题](FAQ.md)——按「看到什么 → 怎么确认 → 怎么恢复」排好序。
- [Python 选做准备](setup/python-basics.md)——只有写脚本或开发时才需要；跑 Docker 不用装。
- [静态观察路线](observe-only.md)——设备装不了软件时学原理，明确不计为「本机跑通」。
- [样板课试学走查指南](walkthrough-guide.md)——给组织者：找两位读者独立试学 04 的任务卡、记录表与判定标准。
- [走查模拟记录](walkthrough-simulation.md)——维护者按两类读者画像做的桌面推演，明确标注非真人；真正的试学结果按走查指南另行记录。
- [教程更新记录](CHANGELOG.md)——增改、验证版本与破坏性变更。
- [五个最小示例](../examples/tutorials/README.md)——四个联网例用标准库调本机 API、一个离线例纯手算，各验证一个机制；都要一份 Python。
- [结课小项目模板](capstone-template.md)——交一份带证据的结论，附一个别人能按版本复跑的实验。

## 开始前需要什么

- **零基础路线**：一台能上网的电脑和浏览器即可；阶段 0 和安装无关。
- **本机跑通**：Docker Desktop（或 Docker Engine + Compose v2），不需要 API Key、GPU 或真实个人数据。
- **写脚本 / 开发**：再加 Python 3.11+，见[选做准备](setup/python-basics.md)。

## 贯穿全系列的三个不变量

1. **证据可追溯**：任何结论都能落到稳定 evidence_id，缺证据就报缺口。
2. **写入有边界**：画像修正要确认，Wiki 写入要乐观并发，后台提交与终态同事务。
3. **数据可收回**：导出、单条删除、账号清理与向量补偿是设计的一部分，不是补丁。

从[开始页](START-HERE.md)起步；已经会 Docker 就从[第 01 篇](01-quickstart.md)开始。
