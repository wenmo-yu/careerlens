# ADR 0030：桌面通知投递

- 状态：Accepted（Windows toast 已实现并有单测；未做通知中心聚合）
- 日期：2026-11-28
- 相关代码：`desktop/src-tauri/src/notifications.rs`、`frontend/lib/desktop.ts`、`frontend/app/agent/page.tsx`

## 问题

通知此前只是应用内派生列表（ADR 0021）：用户不打开窗口就永远看不到待审批或失败的 Run。"通知外发"要的是窗口隐藏时也能感知。

## 决定

用 Windows WinRT toast，由 Rust 命令 `notify(title, body)` 触发：

1. 不引入 Tauri 通知插件：未打包应用没有 AUMID，插件同样要处理注册；这里直接用 `ToastNotificationManager.CreateToastNotifier(aumid)`。
2. 不拼字符串进 PowerShell：toast XML 在 Rust 侧构造并做 XML 转义，脚本通过环境变量读取，`-EncodedCommand` 传参，进程以 `CREATE_NO_WINDOW` 启动。
3. 文本限长（标题 120、正文 300）并过滤控制字符；空标题直接拒绝。
4. 前端只为**新的未读通知**投递一次，`fact_key` 记在 localStorage，最多保留 200 条；投递失败不重试、不改业务状态。

## 边界

- toast 失败不影响通知列表：应用内列表仍是唯一事实源。
- 没有"通知中心"（历史、分组、按类型开关）、没有点击跳转、没有免打扰时段。
- 只在应用运行时投递；关窗后由自启/托盘保活决定是否还能收到（见 ADR 0025）。
- AUMID 固定为 `com.careerlens.desktop`，与 `tauri.conf.json` 的 identifier 一致；改名会让旧通知失去归属。
- 未做 Linux/macOS 投递（当前只发布 Windows NSIS）。

## 验证

- Rust 单测：XML 转义、限长、控制字符、空标题拒绝、base64 编码向量（5 项）。
- 本机手工验证：`CreateToastNotifier('com.careerlens.desktop').Show(...)` 能弹出系统通知。
- 前端 lint/build 通过；投递去重逻辑在浏览器内不触发（`desktopAvailable()` 为假）。

## 回滚

删除 `notify` 命令与前端调用即可；应用内通知列表不受影响。
