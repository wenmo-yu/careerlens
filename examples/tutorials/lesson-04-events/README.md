# 练习 04 · 后台任务与事件

**对应课程**：[06 后台运行时](../../../tutorials/06-runtime.md)
**核对什么**：同键只建一次任务，任务成功后结果可读取，事件以成功收尾。

## 运行

```bash
python3 examples/tutorials/lesson-04-events/main.py
```

前提：Worker 在运行（默认 Compose 已启动）。脚本为 `lesson-04-events` 写入合成证据并重建画像。每次启动脚本生成新的幂等键；同一次脚本的两次提交才共享键。这样重跑不会复用上次失败的任务。任务一直卡在 `queued` 就检查 Worker，见 [FAQ 后台任务](../../../tutorials/FAQ.md#后台任务)。

## 预期输出

```text
教学用户：lesson-04-events
提交得到 run：<ID>（HTTP 202）
同键再提交：<同一个 ID>（HTTP 200，应与第一次相同）
终态：succeeded，attempts=1
岗位分析 ID：<可查询的分析 ID>
事件数：<N>，seq 1 → <末尾序号>，最后是 run.succeeded
OK：同键复用同一任务、结果已保存、事件以成功收尾。
```

`attempts`、事件数取决于运行，脚本只校验关系，不比对固定数字。

## 它验证了什么

- `Idempotency-Key` 是 **HTTP 请求头**，不是请求体字段；同键同输入返回同一个 run（第二次是 200 而非 202）。
- 最多轮询 90 秒；`failed`、`cancelled` 或超时是失败。只有 `succeeded` 且能根据结果 ID 读回岗位分析才继续检查事件。
- 事件非空、属于同一任务，`seq` 严格递增，最后一条是 `run.succeeded`，序号与任务快照一致。

## 负例：省略画像

```bash
python3 examples/tutorials/lesson-04-events/main.py --without-profile
```

负例使用另一个未建画像的教学账号。请求仍能入队并幂等重放，但 Worker 会拒绝执行：出现 `失败：任务终态：failed (invalid_input)`，退出码非零。在 macOS/Linux 用 `echo $?`，在 PowerShell 用 `$LASTEXITCODE` 检查。**这里是负例通过，不是任务成功。**

## 进阶观察

脚本用轮询接口 `/events`。想看 SSE，浏览器打开：

```text
http://localhost:8000/api/v1/runs/<run_id>/stream?user_id=lesson-04-events
```

如果设置过教学账号后缀，用脚本打印的用户 ID 替换 `user_id`。刷新后带上 `after_seq` 可继续读取；本脚本验证的是事件列表，不代替浏览器 SSE 交互测试。
