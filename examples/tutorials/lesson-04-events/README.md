# 练习 04 · 后台任务与事件

**对应课程**：[06 后台运行时](../../../tutorials/06-runtime.md)
**核对什么**：提交任务、幂等键、终态、事件序号。

## 运行

```bash
python3 examples/tutorials/lesson-04-events/main.py
```

前提：Worker 在运行（默认 Compose 已起）。任务一直卡在 queued 就检查 Worker，见 [FAQ 后台任务](../../../tutorials/FAQ.md#后台任务)。

## 预期输出

```text
提交得到 run：<ID>（HTTP 202）
同键再提交：<同一个 ID>（HTTP 200，应与第一次相同）
终态：succeeded，attempts=1
事件数：<N>，seq 1 → <N>
OK：幂等键生效、任务到终态、事件序号递增。
```

`attempts`、事件数取决于运行，脚本只校验关系，不比对固定数字。

## 它验证了什么

- `Idempotency-Key` 是 **HTTP 请求头**，不是请求体字段；同键同输入返回同一个 run（第二次是 200 而非 202）。
- run 会走到终态（`succeeded` / `failed` / `cancelled`）；状态不在终态就继续轮询，最多等 90 秒。
- 事件的 `seq` 严格递增且不重复——SSE 刷新续看就是靠它。

## 进阶观察

脚本用轮询接口 `/events`。想看 SSE，浏览器打开：

```text
http://localhost:8000/api/v1/runs/<run_id>/stream?user_id=lesson-04-events
```

刷新后带上 `after_seq`，进度能从断点接着看。
