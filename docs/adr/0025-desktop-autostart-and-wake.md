# ADR 0025：开机自启与唤醒计划任务

- 状态：Accepted（自启代码与设置界面完成，默认关闭；唤醒任务只提供定义，未在本机注册）
- 日期：2026-11-28
- 相关契约：[`daemon-control-v1.json`](../../contracts/daemon-control-v1.json)
- 相关代码：`desktop/src-tauri/src/autostart.rs`、`frontend/app/settings/page.tsx`、`backend/app/runtime/windows_tasks.py`

## 为什么要自启

持久计划（`agent_schedules`）只有在 scheduler 进程活着时才会执行。应用关闭期间，数据库里只会留下"到过点"这个事实，没有进程去消费它。现有实现是在下次启动时对账（ADR 0024）：把停机窗口内到期的计划按 `skip` / `run_once` 补上。这能保证"不漏"，但不能保证"准时"。

自启解决的是"登录后是否在跑"，让到点变成真正的 Run；唤醒解决的是"到点时机器在睡眠"。两者都不能默认打开：常驻后台和唤醒机器都是对用户设备的实质占用，必须由用户显式选择。

## 决定

**自启**：默认关闭。用户可在 `/settings` 打开，写入当前用户启动项
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `CareerLens` 值，内容为
`"<exe>" --autostart`。

- 选 HKCU 而不是服务或机器级任务：不需要管理员权限、可在任务管理器"启动"里看到并禁用、卸载可逆。
- `--autostart` 启动时窗口只隐藏到托盘，不抢焦点。
- 关闭即删除该值；值不存在视为"已关闭"，不报错。
- 升级/搬移安装目录后记录路径会失配，接口返回 `matches_current_exe=false`，界面提示重新开关一次。

**唤醒**：提供 Task Scheduler 任务定义（`WakeToRun=true`、`InteractiveToken`、`LeastPrivilege`、每 30 分钟、动作 `<exe> --autostart`），但 `register()` 必须显式 `confirm=True`，且应用启动路径里没有任何自动注册。动作指向桌面宿主而不是一次性对账器：只唤醒机器却不启动能执行 Run 的进程，等于把 due 变成排队。

## 验证

- Rust：`command_line` 引号与 `--autostart` 解析有单测（2 项）。
- 前端：设置页在浏览器内只读，桌面内可切换；开关是 `role="switch"` 且带可见焦点。
- 唤醒任务：XML 断言 `WakeToRun`/`LeastPrivilege`/`InteractiveToken`/间隔/动作参数，拒绝无确认注册，非 Windows 拒绝注册（9 项）。
- 未在本机创建真实计划任务（用户明确要求只写代码）。

## 未做与边界

- 真实睡眠/唤醒、断电恢复、DST、注销状态未验证。
- 没有自动更新后的启动项路径修复（只提示用户重新开关）。
- 没有"仅充电时唤醒"或用户可配置的唤醒间隔。
