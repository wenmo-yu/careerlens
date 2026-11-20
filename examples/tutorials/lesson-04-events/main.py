"""练习 04：提交后台任务、验证幂等、轮询事件。

对应课程：tutorials/06-runtime.md
核对：幂等键复用得到同一 run；终态；事件序号递增。
运行：python3 examples/tutorials/lesson-04-events/main.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import check, request  # noqa: E402

USER = "lesson-04-events"
IDEMPOTENCY_KEY = "lesson-04-once"
PAYLOAD = {
    "user_id": USER,
    "operation": "job_analysis",
    "input": {
        "title": "AI Agent 开发",
        "jd_text": "要求熟悉 Python、FastAPI、LangGraph、RAG 与 PostgreSQL；了解 Docker。",
        "weekly_hours": 10,
    },
}
TERMINAL = {"succeeded", "failed", "cancelled"}


def main() -> None:
    hdr = {"Idempotency-Key": IDEMPOTENCY_KEY}
    status, first = request("POST", "/api/v1/runs", body=PAYLOAD, headers=hdr)
    check(status in (200, 202), f"提交失败：{status}")
    run_id = first["id"]
    print(f"提交得到 run：{run_id}（HTTP {status}）")

    # 同键同输入再提交，应拿到同一个 run。
    status2, second = request("POST", "/api/v1/runs", body=PAYLOAD, headers=hdr)
    check(second["id"] == run_id, "幂等键未生效：两次提交得到不同 run")
    print(f"同键再提交：{second['id']}（HTTP {status2}，应与第一次相同）")

    # 带超时轮询状态。
    deadline = time.time() + 90
    state = None
    while time.time() < deadline:
        status, state = request("GET", f"/api/v1/runs/{run_id}?user_id={USER}")
        check(status == 200, f"查询状态失败：{status}")
        if state.get("status") in TERMINAL:
            break
        time.sleep(0.5)
    check(state and state.get("status") in TERMINAL,
          f"90 秒内未到终态，当前：{state.get('status') if state else None}")

    # 事件序号应递增。
    status, events = request(
        "GET", f"/api/v1/runs/{run_id}/events?user_id={USER}&after_seq=0"
    )
    check(status == 200, f"查事件失败：{status}")
    seqs = [e["seq"] for e in events]
    check(seqs == sorted(seqs), "事件序号不是递增的")
    check(len(set(seqs)) == len(seqs), "事件序号有重复")

    print(f"终态：{state['status']}，attempts={state.get('attempts')}")
    print(f"事件数：{len(events)}，seq {seqs[0] if seqs else '-'} → {seqs[-1] if seqs else '-'}")
    print("OK：幂等键生效、任务到终态、事件序号递增。")


if __name__ == "__main__":
    main()
