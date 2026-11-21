"""练习 01：写入一条合成自述，拿到非空 Evidence ID。

对应课程：tutorials/03-parsing.md
运行：python3 examples/tutorials/lesson-01-evidence/main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import check, request, tutorial_user  # noqa: E402

USER = tutorial_user("lesson-01-evidence")


def main() -> None:
    status, payload = request(
        "POST",
        "/api/v1/evidence/text",
        body={
            "user_id": USER,
            "source_type": "self_statement",
            "source_name": "practice-note",
            "content": "我用 Python 做过一个课程项目，只在本机演示。",
        },
    )
    check(status == 201, f"期望 201，实际 {status}")
    items = payload.get("items") or []
    check(len(items) >= 1, "返回里没有 items")
    evidence_id = items[0].get("id")
    check(bool(evidence_id), "Evidence ID 是空的")
    check(items[0].get("content", "").startswith("我用 Python"), "返回内容不对")

    print(f"HTTP {status}，count={payload.get('count')}")
    print(f"返回的证据 ID：{evidence_id}")
    print(f"来源类型：{items[0].get('source_type')}")
    print("OK：拿到非空 Evidence ID。")


if __name__ == "__main__":
    main()
