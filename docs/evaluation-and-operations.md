# 评测、验收与运维

本项目的“能运行”和“建议准确”是两个不同问题。现有测试覆盖基础业务闭环和开发回归；真实用户中的岗位判断质量尚需独立数据集验证。

## 验证矩阵

| 层次 | 当前方法 | 可以证明 | 不能证明 |
| --- | --- | --- | --- |
| 后端测试 | `pytest backend/tests` | 规则、路由和服务的预期行为 | 真实 PostgreSQL/Qdrant 性能或模型质量 |
| 前端检查 | `pnpm lint`、`pnpm build` | 类型/静态检查与可构建 | 浏览器端 E2E 体验 |
| Docker smoke | [`scripts/docker-smoke.ps1`](../scripts/docker-smoke.ps1) | 迁移、健康检查、业务闭环、MCP 鉴权在本机容器环境可运行 | 真实模型、生产流量与公网部署 |
| 合成基准 | 20 场景、80 Evidence、40 检索问题，Recall@5 | 冻结输入下的确定性回归 | 真实简历/JD 的准确率 |

评测实现见 [`backend/app/evaluation/runner.py`](../backend/app/evaluation/runner.py)，数据格式与指标细节见 [`eval/README.md`](../eval/README.md)。当前 v3 冻结基准针对**目录/规则抽取和本地混合检索**计算指标，不是 Qdrant + Qwen + DeepSeek 线上链路的综合效果。Supported Claim Rate 是别名与 Evidence ID 的自动代理校验，不是人工事实判定。即便合成集得分为 100%，也不能写成“真实业务准确率 100%”。

## 本机验收

在项目根目录运行：

```powershell
docker compose up -d --build
.\scripts\docker-smoke.ps1
```

Web 默认在 `http://localhost:3000`，API 文档在 `http://localhost:8000/docs`，MCP 在 `http://localhost:8001/mcp`，Qdrant Dashboard 在 `http://localhost:16333/dashboard`。smoke 成功应输出 `status : passed`，默认还会删除测试账号；用 `-KeepData` 才保留排查数据。Docker 命名卷在 `docker compose down` 后仍保留，`down -v` 会删除卷，不应用于需要保留数据的场景。

## 常见排查路径

| 现象 | 优先检查 |
| --- | --- |
| Web 无法访问 API | `docker compose ps`、API `/health/ready`、浏览器网络请求、前端 API 地址 |
| Evidence 已入库但搜索不到 | 检索诊断中的 `backend/fallback/reason`、Qdrant 健康状态、`/api/v1/evidence/reindex/{user_id}` |
| 模型一直回退 | `AI_PROVIDER`、Base URL、Key、模型名；检查观测摘要中的失败状态，不打印密钥或原文 |
| JD 漏掉技能 | 检查技能别名目录与 `extract_requirements`；当前是规则提取，非任意术语理解 |
| MCP 返回 401/403 | HTTP Token、subject、Scope、API/MCP 是否共用 pepper；区分未认证与权限不足 |
| 数据库 schema 不匹配 | migration job 日志与 Alembic revision；生产环境不要依赖自动建表 |

运行单项检查：

```powershell
pytest backend/tests
ruff check backend
Set-Location frontend
pnpm lint
pnpm build
```

GitHub Actions 配置在 [`.github/workflows/quality.yml`](../.github/workflows/quality.yml)。CI 的具体运行结果以仓库 Actions 页面为准。

## 指标解释

冻结回归门禁的价值在于代码或依赖变化后及时发现结果退化。仓库没有用合成样本的分数推断真实岗位决策的准确率，也没有把默认 Demo Provider 的输出当作真实模型能力。模型比较应在同一份有标注、脱敏且代表目标场景的数据上进行，并同时记录证据引用错误、延迟和成本。
