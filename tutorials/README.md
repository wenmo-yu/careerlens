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
| 0 | 阶段 0：看得懂 | 从材料指出支持证据与「证据不足」 | 计划中（`00-foundations/`）· [开始页第一题](START-HERE.md#我能不能学先花-10-分钟试试)可先练 |
| [01](01-quickstart.md) | 从零跑通 | 本机启动闭环，走一遍数据流 | 已发布 · `docker-compose.yml`、`frontend/app/workspace` |
| [02](02-data-model.md) | 数据模型 | 理解 Evidence、ProfileItem、Run 三张表 | 已发布 · `backend/app/models/` |
| 03 | 解析层 | 结构化解析与 PDF/DOCX/XLSX | 计划中 · `backend/app/ingestion/` |
| 04 | 检索 Agent | 双路召回、RRF、重排、引用校验 | 计划中 · `backend/app/retrieval/`、`backend/app/graph/` |
| 05 | 知识组织 | Wiki 编译、短句柄引用、版本与回滚 | 计划中 · `backend/app/wiki/`、`backend/app/services/wiki_pages.py` |
| 06 | 后台运行时 | 幂等提交、租约、fencing、SSE 续看 | 计划中 · `backend/app/runtime/`、`backend/app/api/routes/runs.py` |
| 07 | 组装与部署 | API 路由、权限、前端任务中心 | 计划中 · `backend/app/api/`、`frontend/components/run-center.tsx` |
| 08 | 进阶 | 真实模型、评测、贡献 | 计划中 · `backend/app/llm/`、`eval/` |

## 工具书与辅助路线

- [术语表](GLOSSARY.md)——第一次遇到先解释，按层集中索引，随查不用背。
- [常见问题](FAQ.md)——按「看到什么 → 怎么确认 → 怎么恢复」排好序。
- [Python 选做准备](setup/python-basics.md)——只有写脚本或开发时才需要；跑 Docker 不用装。
- [静态观察路线](observe-only.md)——设备装不了软件时学原理，明确不计为「本机跑通」。
- [教程更新记录](CHANGELOG.md)——增改、验证版本与破坏性变更。

## 开始前需要什么

- **零基础路线**：一台能上网的电脑和浏览器即可；阶段 0 和安装无关。
- **本机跑通**：Docker Desktop（或 Docker Engine + Compose v2），不需要 API Key、GPU 或真实个人数据。
- **写脚本 / 开发**：再加 Python 3.11+，见[选做准备](setup/python-basics.md)。

## 贯穿全系列的三个不变量

1. **证据可追溯**：任何结论都能落到稳定 evidence_id，缺证据就报缺口。
2. **写入有边界**：画像修正要确认，Wiki 写入要乐观并发，后台提交与终态同事务。
3. **数据可收回**：导出、单条删除、账号清理与向量补偿是设计的一部分，不是补丁。

从[开始页](START-HERE.md)起步；已经会 Docker 就从[第 01 篇](01-quickstart.md)开始。
