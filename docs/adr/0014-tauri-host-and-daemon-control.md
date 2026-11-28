# ADR 0014：Tauri 2 桌面宿主与 Daemon 控制面骨架

- 状态：Accepted（骨架实现；安装包签名与升级未验证）
- 日期：2026-11-28
- 阶段：M2 / M6
- 相关决策：[0001](0001-v4-process-topology-and-ownership.md)、[0005](0005-m0-static-export-packaging-and-job-object.md)、[0007](0007-m1-daemon-supervision-prototype.md)、[0008](0008-daemon-control-protocol-v1.md)、[0009](0009-daemon-implementation-step-one.md)
- 相关契约：[`contracts/daemon-control-v1.json`](../../contracts/daemon-control-v1.json)

## 背景

M0 原型已经证明 Next.js 静态导出、Tauri WebView origin 与本机 CORS 可打通，M1/M2 也已经把进程监督收敛到用户级 daemon 与 `daemon-control-v1`。但仓库里还没有真正的桌面宿主骨架：前端仍按 `standalone` 构建，关窗即退出，没有任何托盘或控制面入口。M2/M6 需要一个可构建、可打包、且不与后端运行时耦合的宿主。

## 决定

### 1. 宿主形态与边界

- `desktop/src-tauri/` 是 Tauri 2 Rust 工程：产品名 `CareerLens`，identifier `com.careerlens.desktop`，版本 `0.4.0`。
- Host 只负责：加载本地静态前端、按需启动 daemon、通过控制面查询/重启/停止、托盘与关窗语义。
- Host **不**直连业务库、**不**替代 FastAPI、**不**自己监督 API/Worker。业务事实仍以 API 与业务库为准，进程事实以 daemon 为准。
- 前端以静态文件进入 WebView。`frontend/next.desktop.config.ts` 复用主配置，覆盖为 `output: "export"`、`images.unoptimized: true`、`trailingSlash: true`；主 `frontend/next.config.ts` 不变。
- Tauri 配置中的 `frontendDist` 是相对 `src-tauri/` 的 `../../frontend/out`，即仓库 `frontend/out`。CSP 只放行 `'self'`、`http://tauri.localhost`（Windows WebView origin）、`http://127.0.0.1:8000`（本地 API）以及 Tauri IPC 所需协议；生产包不允许加载任意远程页面。

### 2. Daemon 启动与命名管道控制

- 启动时读取 `CAREERLENS_DAEMON_EXE`、`CAREERLENS_API_EXE`、`CAREERLENS_DAEMON_PIPE`、`CAREERLENS_DESKTOP_NO_DAEMON`。
- 仅当 daemon exe 已配置且存在、`CAREERLENS_DESKTOP_NO_DAEMON != "1"` 时启动；以 `--api-exe <api_exe>` 传参。若 `CAREERLENS_API_EXE` 为空则**不启动** daemon，只写状态摘要日志。
- 子进程 stdout/stderr 归零，日志只打印状态摘要，不打印业务内容、令牌或提示词。
- 控制客户端按契约走 Windows 命名管道，默认 `\\.\pipe\careerlens-daemon`，可被 `CAREERLENS_DAEMON_PIPE` 覆盖。每次调用使用一条新连接：
  1. 发送一行 `hello`：`{"command":"hello","params":{"protocol":1,"client":"careerlens-desktop","client_version":"0.4.0"}}`；
  2. 校验响应 `ok=true` 且 `protocol=1`；
  3. 再发送目标命令（一行 UTF-8 JSON）：`status`、`restart`（仅 `api`/`worker`）或 `stop`；
  4. 校验 `ok=true` 后把响应交回前端；失败只返回错误码，不回显 daemon 正文。
- 非 Windows 构建提供 no-op stub，保证工程可编译；命令返回明确错误，不触碰任何本地进程。
- Tauri command：`daemon_status()`、`daemon_restart(role)`、`daemon_stop()`。三者只经过控制面；`restart` 的 role 在 Host 侧先按契约白名单校验。
- `stop` 由 daemon 回收其受管子进程；Host 只在 stop 不可达时兜底结束自己拉起的 daemon 进程，且不在退出路径上等待子进程，避免挂死。

### 3. 关窗与退出语义

- 主窗口收到 `CloseRequested` 时 `prevent_close()` 并隐藏窗口；daemon 与 API 不受影响。
- 托盘菜单只有两项：“打开主窗口”与“退出”。左键点击托盘也恢复主窗口。
- “退出”或系统会话关闭触发 Host 退出：先按契约发 `stop`，再退出；daemon 不可达也照样退出。
- `daemon_stop()` 是幂等的：重复调用只报告已请求，不重复发命令。

### 4. 构建与产物

- 静态导出：`pnpm --dir frontend build:desktop`。Next.js 16 已移除 `--config`，因此脚本通过 `desktop/scripts/build-frontend.mjs` 在 `frontend/.desktop-export/`（已忽略）复制源码并安装 `next.desktop.config.ts` 作为该根目录的配置，再构建并同步到 `frontend/out/`；主配置始终不被改写。
- CI：`.github/workflows/desktop-release.yml` 在 `desktop-v*` tag 与手动触发时运行：ubuntu 做静态导出与 `cargo check`，windows-latest 做 Tauri build、上传 NSIS 产物与 SHA256、写发布摘要。未配置签名 secret 时产物只能作为 unsigned RC，不得标为 stable。

## 本机构建证据

在本地 Windows（Rust 1.100.0 + MSVC、Node 22.22.2、Tauri CLI 2.12.6）执行：

| 命令 | 结果 |
| --- | --- |
| `pnpm --dir frontend build:desktop`（经 `build:desktop` 脚本） | Next.js 16.4.6 静态导出成功；路由 7 个：`/`、`/_not-found`、`/architecture`、`/demo`、`/icon.svg`、`/start`、`/workspace` |
| `cargo check --offline --manifest-path desktop/src-tauri/Cargo.toml` | `Finished dev profile` |
| `tauri build --ci`（在 `desktop/src-tauri`） | `Finished release profile`；产出 `careerlens-desktop.exe` 与 NSIS `CareerLens_0.4.0_x64-setup.exe`（12.50 MiB，SHA256 `887d4be99a639911a4a9f88c6264bb56fb7b3145070b04665838705c82af4623`） |

以上是本机构建证据，不是安装/运行验收。构建产物与 `frontend/out/` 均被 `.gitignore` 排除，未提交。

## 替代方案与取舍

- **网页套壳（浏览器/固定 localhost 页面）**：拒绝。无法承担 daemon 生命周期、托盘驻留与关窗后台语义；WebView origin 也无法保证静态资源与 API 的可控边界。
- **Host 直连 API / 自建 HTTP 控制口**：拒绝。HTTP 回环对任何本机进程开放，需要另建令牌体系；命名管道可按 SID 限定，且契约已经冻结。
- **Host 自己管理 API/Worker 进程**：拒绝。会与 daemon 形成第二个进程权威，重复实现 Job Object、重启计数与单实例锁，破坏 ADR 0007/0009 的所有权边界。
- **改动主 `next.config.ts` 做导出**：拒绝。主配置服务 `standalone` 部署，桌面导出必须是可并存的第二条构建路径。

## 风险与未验证项

- 未验证：真实安装/卸载、签名、自动更新与 rc 渠道发布；CI 的签名 secret 只是占位。
- 未验证：打包后的 Host 与真实 daemon 端到端联通（本机只做到 Host 构建与静态导出，没有在安装包里跑业务链路）。
- 未验证：用户试学与真实 Run/SSE 链路在桌面包内的表现；后端 CORS 是否包含 `http://tauri.localhost` 仍需在部署配置中显式确认。
- 非 Windows 上仅保证编译与控制面 no-op，托盘/关窗行为未验证。
- Next.js 16 静态导出依赖当前版本行为；升级后需重跑 7 路由与资源引用检查。

## 回滚

删除 `desktop/`、本 ADR 与索引条目，撤销 `frontend/next.desktop.config.ts`、`frontend/package.json` 的 `build:desktop` 脚本及 `.gitignore` 末尾的桌面构建规则，并删除 `.github/workflows/desktop-release.yml`。不影响后端、主前端配置与既有 CI。
