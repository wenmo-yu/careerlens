"""Run the published exercises twice against an isolated CareerLens Demo."""

import os
import platform
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from _client import check, request

LESSONS = {
    "lesson-01-evidence": ("lesson-01-evidence",),
    "lesson-02-dedup": ("lesson-02-dedup-a", "lesson-02-dedup-b"),
    "lesson-03-chat-modes": ("lesson-03-chat-modes",),
    "lesson-04-events": ("lesson-04-events",),
}
NO_PROFILE_USER = "lesson-04-events-no-profile"
EXPECTED_FAILURE = "失败：任务终态：failed (invalid_input)"


def run_lesson(
    lesson: str, label: str, base: str, env: dict[str, str], *, negative: bool = False
) -> bool:
    script = Path(__file__).resolve().with_name(lesson) / "main.py"
    command = [sys.executable, "-B", str(script), base]
    if negative:
        command.append("--without-profile")
    try:
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"{label} {lesson}: timeout", flush=True)
        return False

    print(f"{label} {lesson}: exit={result.returncode}", flush=True)
    print(result.stdout + result.stderr, end="", flush=True)
    if negative:
        return (
            result.returncode != 0
            and EXPECTED_FAILURE in result.stderr
            and "OK：" not in result.stdout
        )
    return result.returncode == 0 and "OK：" in result.stdout


def smoke(base: str, local_demo: bool) -> None:
    health_path = "/health/live" if local_demo else "/health/ready"
    _, readiness = request("GET", health_path, base=base)
    check(readiness["status"] == "ok", "Demo API 未就绪")
    if not local_demo:
        check(
            readiness["checks"] == {"database": "ok", "qdrant": "ok"},
            "Compose 门禁要求数据库与 Qdrant 都已就绪",
        )

    namespace = f"smoke-{uuid4().hex}"
    env = {
        **os.environ,
        "CAREERLENS_TUTORIAL_NAMESPACE": namespace,
        "CAREERLENS_TUTORIAL_REQUIRE_QDRANT": "0" if local_demo else "1",
        "PYTHONIOENCODING": "utf-8",
    }
    print(f"Python {platform.python_version()} | {health_path} | {namespace}", flush=True)
    failures = []
    cleaned = 0
    try:
        for label in ("first", "rerun"):
            for lesson in LESSONS:
                if not run_lesson(lesson, label, base, env):
                    failures.append(f"{label}/{lesson}")
        if not run_lesson("lesson-04-events", "negative", base, env, negative=True):
            failures.append("negative/lesson-04-events")
    finally:
        users = [user for names in LESSONS.values() for user in names] + [NO_PROFILE_USER]
        for name in users:
            user_id = f"{name}-{namespace}"
            try:
                _, receipt = request("DELETE", f"/api/v1/privacy/{user_id}", base=base, timeout=10)
                check(receipt.get("deleted") is True, "未得到删除回执")
                cleaned += 1
            except (AssertionError, RuntimeError, TimeoutError, ValueError) as exc:
                print(f"cleanup {user_id}: {exc}", file=sys.stderr)
                failures.append(f"cleanup/{name}")
        print(f"Cleaned up {cleaned}/{len(users)} isolated tutorial users.", flush=True)

    check(not failures, f"教学冒烟未通过：{', '.join(failures)}")
    print("Four lessons passed on first run and rerun; missing-profile case failed as expected.")


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("api_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--local-demo", action="store_true", help="允许不含 Qdrant 的本地 Demo")
    args = parser.parse_args()
    base = args.api_url.rstrip("/")
    url = urlsplit(base)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or url.username is not None
        or url.path
        or url.query
        or url.fragment
    ):
        parser.error("只能对本机隔离的 HTTP Demo 运行此检查")
    try:
        smoke(base, args.local_demo)
    except (AssertionError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(f"失败：{exc}") from None


if __name__ == "__main__":
    main()
