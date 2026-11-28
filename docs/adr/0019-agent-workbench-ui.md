# ADR 0019：Agent 工作台最小界面

- 状态：Accepted（静态导出与构建通过；真实桌面用户体验未验证）
- 日期：2026-11-28
- 相关代码：`frontend/app/agent/page.tsx`、`frontend/lib/api.ts`、`frontend/components/site-sidebar.tsx`

## 决定

新增 `/agent` 页面作为 V4 Agent 面的最小可观察界面，不改写现有 `/workspace` 的画像、岗位、报告和 Copilot 流程。

页面只做四件事：

1. 选择用户标识（已登录时从 `/auth/me` 读取）并创建/列出 Agent 会话；
2. 选择会话、提交一轮消息并读取持久消息历史；
3. 展示待审批工具并允许批准/拒绝；
4. 展示 runtime/status 与 capabilities，明确提示 scheduler 未启动时 Run 会停在 `queued`。

所有数据来自现有 API，不在前端维护第二份会话或事件权威。每轮提交生成稳定 `Idempotency-Key`；消息和审批通过 2.5 秒轮询刷新，关闭页面不会取消后台 Run。

## 为什么不是完整桌面三栏

V4 的完整桌面形态仍需要真实 WebView 内审批、连接切换、重连与 `stream_generation`。当前页面是可验证的最小闭环，优先让持久契约、审批和状态可见；不把未验证的 UI 交互写成完成。

## 验证

- `pnpm lint`、`pnpm test`、`pnpm build` 全部通过；主配置仍为 standalone。
- 字体改为本地 CSS 栈，不再在构建时请求 `fonts.gstatic.com`，受限网络下也能构建。
- 静态导出包含 `/agent` 路由（构建完成后确认）。
- 页面使用现有 `request<T>` 与 token/session 边界，没有新增认证机制。

## 边界

- 没有 SSE 实时流，只有轮询；没有会话切换时的事件 epoch 丢弃。
- 没有任务树、团队邮箱和计划的可视化编辑。
- 没有真人试学、窄窗口/键盘/深浅色验收。

## 回滚

删除 `/agent` 页面、新增的 API 客户端函数与侧栏入口即可；不影响 `/workspace` 或后端契约。
