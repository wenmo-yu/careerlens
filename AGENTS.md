# AI 查阅入口（不是给人看的）

本文件是 CareerLens 仓库的 AI 入口。进入本仓库做任何代码、教程、文档、站点或发布相关任务前，先读 [`AI_CONTEXT.md`](AI_CONTEXT.md)，再按其中的「任务 → 先读文件」表定位源码。

## 硬规则

1. **先读导航，再读代码**。不要在 `backend/`、`frontend/`、`docs-site/`、`tutorials/` 里无目的全量遍历。
2. **当前事实以源码 + `CHANGELOG.md` + `docs/README.md` + 本地 `CareerLens文档导航.md` 为准**；早期草案、验收快照、历史 commit 只用于追溯，不作为当前依据。
3. **忽略缓存和依赖目录**：`.git/`、`.venv/`、`node_modules/`、`.next/`、`__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`.ruff_cache/`、`.cache/`。它们不是项目源码。
4. **`app.asar.extracted/`、`weknora-source/` 在工作区根目录，不是本仓库源码**，只在明确做对照研究时读取。
5. **前端框架 API 例外**：`frontend/AGENTS.md` 是 Next.js 自动生成并维护的规则；写前端代码时仍须遵守它，并在需要时读取 `frontend/node_modules/next/dist/docs/`。
6. **本地 git 的 `ahead` / 旧 `HEAD` 不是权威状态**。远端 `main`、GitHub Actions 和线上 Pages 才是权威；本轮通过 Git Data API 推送，本地跟踪引用可能滞后。
7. **新增、删除、重命名文件或目录后，必须同步更新 `AI_CONTEXT.md`**，否则导航会失真。
8. 本地管理文档（台账、验收报告、历史归档）在仓库外，与 `careerlens/` 并排；入口是 [`../CareerLens文档导航.md`](../CareerLens文档导航.md) 和 [`../AI查阅导航.md`](../AI查阅导航.md)。

如果你只想查某一类问题，直接在 `AI_CONTEXT.md` 里搜索「改…先读」「以前」「现在」「不要读」。
