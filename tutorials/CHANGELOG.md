# 教程更新记录

记录教程体系的增改、验证过的代码版本与破坏性变更。与产品 [`CHANGELOG.md`](../CHANGELOG.md) 分开维护：那个记录代码版本，这个记录课程。

未发布篇章在[进度总览](README.md)里标为「计划中」，不在此处提前登记为已交付。

## 课程 v1.0（筹备中）

目标：零基础可见、可跑通、有在线教程站。范围以 [`CareerLens零基础教程体系方案`](https://github.com/wenmo-yu/careerlens) 与仓库内 `README` 为准；第 4 批（Docsify 站点）完成后再打 `docs-tutorials-v1.0` 快照标签。

### 第 1 批 · 入口与首次运行（进行中）

- 新增 [`START-HERE.md`](START-HERE.md)：两条学习路线、按时间选学法、阶段成果、零安装第一题（含自查）、何时装软件、求助方式。
- 新增 [`GLOSSARY.md`](GLOSSARY.md)：按概念 / 检索 / 知识组织 / 运行时 / 隐私分层解释术语。
- 新增 [`FAQ.md`](FAQ.md)：按启动、就绪与 API、数据、后台任务、模型与数据分类，统一「看到什么 → 怎么确认 → 怎么恢复」。
- 新增 [`observe-only.md`](observe-only.md)：无法安装软件时的静态观察路线，明确不计为「本机跑通」。
- 新增 [`setup/python-basics.md`](setup/python-basics.md)：Python 选做准备，与 Docker 起步步骤解耦。
- 改造 [`01-quickstart.md`](01-quickstart.md)：
  - 就绪接口由误写的 `/api/v1/health/ready` 更正为 `/health/ready`；
  - 本机准备按 Windows / macOS 分列，补充 Linux 官方入口；
  - 命令逐行解释，补充 `docker compose down`（不加 `-v`）与端口冲突处理；
  - Swagger 的「重做一遍 API」改为接口操作说明，不再把接口名与 JSON 标成 PowerShell 命令；
  - Python 安装移入选做，静态观察路线另放入口。
- 更新根 `README.md` 与 [`docs/README.md`](../docs/README.md) 的教程导航，统一指向零基础入口。

**验证状态**：本批内容以代码核对为准，健康路径、端口、返回字段、Compose 服务均已对照实现与冒烟脚本；Windows / macOS / Linux 的实际安装走查按实施方案逐系统记录，未实测组合会在对应篇章明确标注。

### 第 2 批 · 阶段 0（计划中）

四篇 `00-foundations/`，统一使用虚构人物林澈与同一组教学卡片。收藏卡按兴趣线索处理；「纯文本导入被 Demo 误认成技能」留到阶段 5 的对照实验。

### 第 3 批 · 实现篇与练习（计划中）

`03`–`08` 实现与进阶篇、四个最小练习 `examples/tutorials/`、结课小项目模板。

### 第 4 批 · Docsify 在线教程站（计划中）

发布工作流、站点壳、README 在线教程链接与快照标签；验收通过后才在 README 挂站点入口。

## 约定

- 每篇课头标注已验证的代码 tag 或 commit，避免「课程用一版、下载用另一版」。
- 破坏性变更（路径、端口、字段、Schema 改名）在本文件顶部单独注明，并同步检查相邻篇章与 `docs/api-and-configuration.md`。
- 小修（错别字、断链、截图更新）直接记入当批条目，不单独开版本。
