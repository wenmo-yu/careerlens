"""练习 04：提交后台任务、验证幂等、轮询事件。

对应课程：tutorials/06-runtime.md
核对：幂等键复用得到同一 run；任务成功并有结果；事件序号递增。
运行：python3 examples/tutorials/lesson-04-events/main.py
"""
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import DEFAULT_BASE, check, prepare_profile, request, tutorial_user  # noqa: E402

JOB = {
    "title": "AI Agent 开发",
    "jd_text": "要求熟悉 Python、FastAPI、LangGraph、RAG 与 PostgreSQL；了解 Docker。",
    "weekly_hours": 10,
}


def submit_job(user_id: str, base: str) -> str:
    payload = {"user_id": user_id, "operation": "job_analysis", "input": JOB}
    headers = {"Idempotency-Key": uuid4().hex}
    status, first = request("POST", "/api/v1/runs", body=payload, headers=headers, base=base)
    check(status == 202 and bool(first["id"]), f"第一次提交应该创建任务（202），实际：{status}")
    run_id = first["id"]
    print(f"提交得到 run：{run_id}（HTTP {status}）")

    status, second = request("POST", "/api/v1/runs", body=payload, headers=headers, base=base)
    check(status == 200 and second["id"] == run_id, "同键同输入未返回原任务（200）")
    print(f"同键再提交：{second['id']}（HTTP {status}，应与第一次相同）")
    return run_id


def wait_for_success(run_id: str, user_id: str, base: str) -> dict:
    deadline = time.monotonic() + 90
    last_status = "unknown"
    while (remaining := deadline - time.monotonic()) > 0:
        _, state = request(
            "GET", f"/api/v1/runs/{run_id}?user_id={user_id}", base=base, timeout=min(remaining, 30)
        )
        last_status = state["status"]
        if last_status == "succeeded":
            return state
        check(
            last_status not in {"failed", "cancelled"},
            f"任务终态：{last_status} ({state.get('error_code')})",
        )
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise AssertionError(f"90 秒内未成功，当前：{last_status}；请确认 Worker 正在运行")


def main() -> None:
    parser = ArgumentParser(description="验证 CareerLens Demo 后台任务和事件。")
    parser.add_argument("api_url", nargs="?", default=DEFAULT_BASE)
    parser.add_argument("--without-profile", action="store_true", help="负例：省略准备画像，应失败")
    args = parser.parse_args()
    base = args.api_url.rstrip("/")
    name = "lesson-04-events-no-profile" if args.without_profile else "lesson-04-events"
    user_id = tutorial_user(name)
    print(f"教学用户：{user_id}")
    if not args.without_profile:
        prepare_profile(user_id, base=base)

    run_id = submit_job(user_id, base)
    state = wait_for_success(run_id, user_id, base)
    check(not args.without_profile, "负例没有画像却跑成功；请确认负例教学账号未被预先写入")
    analysis_id = (state.get("result") or {}).get("job_analysis_id")
    check(isinstance(analysis_id, str) and bool(analysis_id), "任务成功但没有岗位分析 ID")
    _, analysis = request("GET", f"/api/v1/jobs/{analysis_id}", base=base)
    check(analysis["id"] == analysis_id and analysis["user_id"] == user_id, "岗位分析结果不匹配")

    _, events = request(
        "GET", f"/api/v1/runs/{run_id}/events?user_id={user_id}&after_seq=0", base=base
    )
    seqs = [event["seq"] for event in events]
    check(bool(seqs) and seqs == sorted(set(seqs)), "事件序号为空、乱序或重复")
    check(all(event["run_id"] == run_id for event in events), "事件不属于本任务")
    check(
        events[-1]["event_type"] == "run.succeeded" and seqs[-1] == state["event_seq"],
        "事件流没有以当前任务的成功事件收尾",
    )

    print(f"终态：{state['status']}，attempts={state.get('attempts')}")
    print(f"岗位分析 ID：{analysis_id}")
    print(f"事件数：{len(events)}，seq {seqs[0]} → {seqs[-1]}，最后是 run.succeeded")
    print("OK：同键复用同一任务、结果已保存、事件以成功收尾。")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(f"失败：{exc}") from None
