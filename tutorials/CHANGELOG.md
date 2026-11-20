# 教程更新记录

记录教程体系的增改、验证过的代码版本与破坏性变更。与产品 [`CHANGELOG.md`](../CHANGELOG.md) 分开维护：那个记录代码版本，这个记录课程。

未发布篇章在[进度总览](README.md)里标为「计划中」，不在此处提前登记为已交付。

## 课程 v1.0（已发布）

在线教程站：**https://wenmo-yu.github.io/careerlens/**
快照标签：`docs-tutorials-v1.0`

目标已完成：零基础可见（阶段 0 零安装）、可跑通（01–08 与四个示例）、有在线教程站。范围以仓库 `README` 与教程总览为准。后续小修直接记入本文件，不再另发产品版本。

### 第 1 批 · 入口与首次运行（已合并）

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

### 第 2 批 · 阶段 0（已合并）

四篇 `00-foundations/` 全部发布，统一使用虚构人物林澈与同一组教学卡片，严格零安装、只用浏览器，每篇含一张图（Mermaid + 文字替代）、先做后看的练习与常见误判：

- `00-1-what-is-agent.md`：分清语言模型、固定流程与 Agent，不迷信 Agent。
- `00-2-prompt-and-evidence.md`：提示词三要素；收藏≠掌握、岗位要求≠经历、做过≠熟练。收藏卡按兴趣线索处理。
- `00-3-rag-and-vector.md`：关键词与语义两条检索线索；「相关 ≠ 支持」；纸面模拟，不冒充在线推理。
- `00-4-data-model-in-plain-words.md`：证据→画像→岗位匹配→缺口→学习计划→报告；示意编号与真实编号的区别。

「纯文本导入被 Demo 误认成技能」按方案留到阶段 5 的对照实验，不在入门制造矛盾。同步更新 `START-HERE.md`、`README.md`、`GLOSSARY.md` 的阶段 0 链接。

### 第 3 批 · 实现篇与练习（已合并）

`03`–`08` 实现与进阶篇、四个最小练习 `examples/tutorials/`、结课小项目模板。

- `03-parsing.md`（已交付）：解析与去重、支持格式、扫描页不伪造文字、`source_metadata` 定位字段；含最小去重函数复刻题。
- `04-retrieval-agent.md`（已交付）：Dense+Sparse → RRF → 两级重排 → 引用核验；三种模式切换与诊断字段；wiki 模式诊断缺 backend 键的诚实说明。
- `05-wiki.md`（已交付）：短句柄 `c000`、表格行守卫、版本不变量、`base_version` 乐观并发、回滚即普通编辑。
- `06-runtime.md`（已交付）：Run/Step/Event 状态机、`Idempotency-Key`、`interrupted` vs `cancelled`、租约、fencing 代次、SSE `after_seq` 续看、Worker 必需。
- `07-integration.md`（已交付）：系统全景、三种状态区分、评测接口路径与口径、API/MCP 共用业务服务。
- `08-advanced/08-1-real-models.md`（已交付）：Demo vs 真实链路、`AI_PROVIDER` 无 `qwen` 值、收藏卡对照实验。
- `08-advanced/08-2-evaluation.md`（已交付）：四项指标、复跑冻结基线、开发集分数边界。
- `08-advanced/08-3-contribute.md`（已交付）：可复查 PR、结课项目结构。
- `examples/tutorials/`（已交付）：四个标准库脚本（证据、去重、三模式、事件）+ 索引；`tutorials/capstone-template.md` 结课模板。

接口与字段逐条对照源码核对：chat 的 `mode` 是请求体字段、诊断在 `retrieval`、证据在顶层 `evidence`；wiki 编译的同步接口与后台 run 两种方式的 `edit_source` 差异；`Idempotency-Key` 是请求头；评测接口无裸 `/evaluation`。

**运行验证状态**：四个示例脚本已通过 Python 语法编译检查；本环境无 Docker，**未能在运行中的服务上实测执行**，脚本所依赖的接口/字段已静态核对源码。到有 Docker 的环境按 `examples/tutorials/README.md` 跑一遍即可确认。

### 第 4 批 · Docsify 站点（已合并并上线）

Docsify 站点壳（`docs-site/`）、固定版本本地资源、打包脚本、GitHub Pages 工作流均已合并进 main。PR #20 的 build / backend / frontend / docker-smoke 四项 CI 全绿；期间修复过一次漏交的 `.nojekyll`。

**部署**：仓库管理员在 Settings → Pages 把 Source 设为 GitHub Actions 后重新触发部署成功。线上 `https://wenmo-yu.github.io/careerlens/` 首页、Docsify 资源、START-HERE、侧栏均返回 HTTP 200，页面标题与 `homepage` / `basePath` 配置正确。

### 第 5 批 · 教程 v1.0 发布收尾（已交付）

- 根 `README.md` 顶部与教程段、`START-HERE.md` 常用入口加入在线教程链接；GitHub 阅读入口保留。
- 课程状态标记为 v1.0 已发布。
- 打 `docs-tutorials-v1.0` 快照标签（不触发产品 Release，现有 `release.yml` 只匹配 `v*`）。

**上线验收口径**：首页 / 资源 / 篇章 / 侧栏的 HTTP 可达性与配置已核对；搜索框、代码复制按钮、Mermaid 实际渲染、`<noscript>` 降级、深链接刷新属于浏览器交互项，建议在手机和桌面各点检一次（本地无无头浏览器工具，未自动测）。

### v1.0 修复 · Docsify 主题样式缺失（PR #23）

站点上线后用户反馈页面呈纯文本、右上角 GitHub 角标被放大成黑底蓝猫，看似崩坏。根因是 `docs-site/index.html` 漏引 Docsify 主题 CSS——`docsify.min.js` 只负责逻辑，不含布局样式，需单独引入主题表。结果是正文、侧栏、顶栏、角标全部失去样式。

修复：新增固定版本 `vendor/docsify-theme.css`（`docsify@4.13.1/lib/themes/vue.css`，去掉 Google Fonts `@import` 实现完全本地化），在 `index.html` 引入，`VERSIONS.md` 记录版本。

验证：无头 Chrome 对本地打包产物截图，确认侧栏、标题层级、表格、提示框、GitHub 角标正常；深链接页的搜索框、Mermaid、表格渲染检查通过。此修复解释了此前"浏览器交互未自动测"的遗留项——当时无无头浏览器，现已补上并发现真实问题。

## 约定

- 每篇课头标注已验证的代码 tag 或 commit，避免「课程用一版、下载用另一版」。
- 破坏性变更（路径、端口、字段、Schema 改名）在本文件顶部单独注明，并同步检查相邻篇章与 `docs/api-and-configuration.md`。
- 小修（错别字、断链、截图更新）直接记入当批条目，不单独开版本。
