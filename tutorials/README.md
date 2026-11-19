# CareerLens 实现教程

这一系列教程的目标不是"教你怎么用 CareerLens"，而是**带你一层层把它做出来**。读完后你应该能理解每个模块为什么存在、它和上下游如何衔接，并能在一个最小项目里复刻核心机制。

教程按依赖顺序编排。每一篇都遵循同一结构：**目标 → 前置 → 步骤 → 验收**， Step 里有可直接运行的代码或命令，验收有明确的"做到什么算完成"。

## 学习路径

```text
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
```

## 教程目录

| 序号 | 主题 | 你将实现 | 对应源码 |
| --- | --- | --- | --- |
| [01](01-quickstart.md) | 从零跑通 | 本地启动完整闭环，理解一次请求的数据流 | `docker-compose.yml`、`frontend/app/workspace` |
| [02](02-data-model.md) | 数据模型 | Evidence、ProfileItem、Run 三张表及迁移 | `backend/app/models/` |
| 03 | 解析层 | 结构化解析契约与 PDF/DOCX/XLSX 解析 | `backend/app/ingestion/` |
| 04 | 检索 Agent | 双路召回、RRF、重排、引用校验的 LangGraph 流程 | `backend/app/retrieval/`、`backend/app/graph/` |
| 05 | 知识组织 | Wiki 编译、短句柄引用、版本与回滚 | `backend/app/wiki/`、`backend/app/services/wiki_pages.py` |
| 06 | 后台运行时 | 幂等提交、租约、fencing、SSE 续看 | `backend/app/runtime/`、`backend/app/api/routes/runs.py` |
| 07 | 组装与部署 | API 路由、权限、前端任务中心、质量门禁 | `backend/app/api/`、`frontend/components/run-center.tsx` |

> 已完成的篇章为可点击链接（当前 01、02），其余列在路线图中、按依赖顺序陆续补充。每篇都尽量可独立阅读；顺序阅读能建立最完整的系统观。未完成篇章可先按"对应源码"一栏自行探索。

## 贯穿全系列的三个不变量

1. **证据可追溯**：任何结论都能落到稳定 evidence_id，缺证据就报缺口。
2. **写入有边界**：画像修正要确认，Wiki 写入要乐观并发，后台提交与终态同事务。
3. **数据可收回**：导出、单条删除、账号清理与向量补偿是设计的一部分，不是补丁。

## 开始前

- 环境：Docker Desktop（或 Docker Engine + Compose v2）、Python 3.11+、Node.js 20.9+
- 基础：用过 FastAPI 或任一 Python Web 框架；了解向量检索的基本概念
- 不需要：真实模型密钥、GPU 或任何个人数据

先从[第 01 篇：从零跑通](01-quickstart.md)开始。
