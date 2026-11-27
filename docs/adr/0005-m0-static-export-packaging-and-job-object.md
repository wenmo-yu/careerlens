# ADR 0005：M0 静态导出、Python 打包与 Job Object 原型边界

- 状态：Accepted（仅原型证据，不代表完整 Desktop 产品发布或沙箱验收）
- 日期：2026-11-27
- 阶段：M0
- 相关规范：V4 §16.1、§18.1、§18.3
- 相关决策：[0001](0001-v4-process-topology-and-ownership.md)、[0004](0004-m0-scripted-runner-prototype.md)
- 参考测试：T01、T04、T05、T16

## 背景

M0 除自研 Runner 外，还需要证明 Web 前端能被静态导出、后端能被打包成可启动的 Windows 进程，以及本机进程约束是否至少能阻断子进程与随宿主退出。这些结论决定 Tauri 是否需要拆 Vite 桌面入口、打包器要固定哪些依赖，以及高风险工具能否先只允许低权限调用。

## 决定与证据

### 1. Next.js 静态导出与最小 Tauri 宿主已构建、已启动

- 临时把 `frontend/next.config.ts` 的 `output` 从 `standalone` 改为 `export`，用 Node 22.22.2 运行 `node node_modules/next/dist/bin/next build`；Next.js 16.4.6 + Turbopack 构建成功。
- 生成 7 个静态路由：`/`、`/_not-found`、`/architecture`、`/demo`、`/icon.svg`、`/start`、`/workspace`。没有 server-only API 或动态渲染报错。
- HTML 中的 22 个 `/_next/...` 资源引用都能在构建目录内找到；路径是绝对路径，因此 Tauri 必须以 origin 根提供静态资源，不能假定相对路径直接可用。
- 构建后配置已恢复为 `standalone`，仓库树保持干净。
- 在仓库外搭了最小 Tauri 2 宿主（tauri 2.12.7、wry 0.57.4、webview2-com 0.39.1），用 MSVC 工具链编译成功；首次失败仅因缺少 `icons/icon.ico`，补最小图标后 `cargo build --release` 通过，exe 能启动并创建 WebView 窗口。
- WebView 内实测 origin 为 `http://tauri.localhost`；页面引用的 16 个静态资源请求全部返回 200。绝对路径 `/_next/...` 在该 origin 下可解析。
- **CORS 是 Desktop 必须处理的真实问题**：默认 `CORS_ORIGINS` 不含 `http://tauri.localhost` 时，WebView 内 `/health/live`、证据导入和 chat 请求全部失败；把该 origin 加入后端 `CORS_ORIGINS` 后，health 返回 200、`POST /api/v1/evidence/text` 返回 201、chat 请求到达业务层并返回 422「Build the user profile before chatting」。这说明网络链路已打通，chat 后续需要真实画像；Run SSE 的完整持久流仍未验证。

结论：ADR 0001 的首选 Tauri 路线通过 M0 原型，不启用"共享 UI + Vite 桌面入口"回退。实现 PR 必须显式配置 Desktop origin（或改走 Tauri IPC 代理），不能依赖浏览器默认 CORS。

### 2. Python 后端可打包为可启动 exe，但依赖来源需固定

- 在隔离 Python 3.13.14 环境用 PyInstaller 6.22.3 构建 `backend/app.main` 的 onefile 原型，产物约 114 MB。
- 首次运行发现动态导入缺失：`asyncpg` 与 `aiosqlite`。加入显式 `--hidden-import aiosqlite,asyncpg,uvicorn,qdrant_client,prometheus_client` 后，exe 能导入应用并打印版本。
- 加入服务模式后，打包 exe 启动 uvicorn 于 `127.0.0.1:8123`，`GET /health/live` 返回 HTTP 200 `{"status":"ok"}`。
- 本机依赖来自 `pip install -e ".[dev]"`（与当前 CI 相同），不是 `backend/uv.lock`；原型环境打印的 `app.version` 为 `0.0.0`，与项目 `0.4.0` 不同，说明版本注入方式必须在实现 PR 中固定。
- 在同一个打包 exe 上实测：`POST /api/v1/evidence/text` 成功写入 self_statement 证据；`POST /api/v1/evidence/file` 上传合成 `.txt` 后返回 `parse_status=parsed`、`readable_count=1`、`source_document_id`。基础文本与文件解析链在打包产物中可用。
- PDF/DOCX/XLSX、OCR/ASR、真实模型以及依赖锁定版本没有在打包产物中验证，不能据此宣称完整 Desktop 后端可用。

结论：M0-03 的"打包、启动 API、基础解析"通过；"全格式解析、真实依赖锁定与真实模型"仍待验证。

### 3. Windows Job Object 只证明两项进程约束

本地一次性 ctypes 原型（含机器相关路径，未进入公开仓库）验证：

- `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`：关闭 job 句柄后，受管子进程被终止。
- `JOB_OBJECT_LIMIT_ACTIVE_PROCESS=1`：受管子进程尝试再生子进程时，观察到 CreateProcess 失败，判定为 `spawn_blocked`。
- 边界：子进程自身以异常码退出，说明这是"限制被触发"的证据，不是完整攻击矩阵；没有证明文件、网络、命名管道隔离，也没有验证嵌套 job、句柄继承或宿主已在一个 job 中的失败路径。
- AppContainer 前置检查：本机可调用 `userenv.dll` 的 profile API，创建 SID 成功（HRESULT 0），`FreeSid` 与删除 profile 也成功（HRESULT 0）。这仅是 profile 生命周期验证；没有启动受限进程，也没有验证文件/网络能力边界。

结论：高风险工具仍必须经过 Tool Gateway 与能力门；Job Object 不能单独作为沙箱成立的依据。

## 替代方案与取舍

- **为此把核心换成 OpenAI Agents SDK**：WorkBuddy 使用了该 SDK 作为循环底座，但同时维护 ACP 外壳、AgentService、ToolManager 与产品补丁；CareerLens 的状态权威、自定义 JSONL v1 和证据/审批事务与 SDK 内部状态不同。本轮继续自研，SDK 只作设计学习材料，见本地计划的判断记录。
- **先做完整 Tauri 安装包**：最小宿主与 WebView 基础链路已验证，但安装包签名、自动更新、真实登录画像和 Run SSE 未完成；先固定可复现的原型证据，避免把构建失败误判为前端问题。
- **把 Job Object 结果写成沙箱完成**：拒绝。只记录已观察到的两项限制，未验证的隔离面继续标为待验。

## 风险与回滚

- 静态导出依赖 Next.js 16.4.6 的当前行为；升级版本需重跑构建与资源检查。
- Desktop origin 必须进入后端 CORS 允许列表；若改用 Tauri IPC 代理，需要重新验证鉴权、SSE 与上传语义，不能以"同源"为由跳过。
- PyInstaller 隐藏导入清单可能随 FastAPI/SQLAlchemy/客户端库升级变化；每次升级都要重跑 exe 健康端点。
- 打包环境的版本来自 pip 解析，不等于 lockfile；实现 PR 必须同时记录锁定版本与实际安装版本。
- 回滚：本 ADR 只记录证据；不新增运行时代码。若后续静态导出或打包失败，回退到 ADR 0001/0004 的既有边界，不删减 V4 最终能力。
