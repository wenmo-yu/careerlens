"""练习 02：验证证据去重。

对应课程：tutorials/03-解析层.md
核对：同一用户导入两次 → ID 复用；不同用户 → 不复用。
运行：python3 examples/tutorials/lesson-02-dedup/main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import check, request, tutorial_user  # noqa: E402

USER_A = tutorial_user("lesson-02-dedup-a")
USER_B = tutorial_user("lesson-02-dedup-b")
CONTENT = "我用 Python 做过一个课程项目，只在本机演示。"


def ingest(user: str) -> str:
    status, payload = request(
        "POST",
        "/api/v1/evidence/text",
        body={
            "user_id": user,
            "source_type": "self_statement",
            "source_name": "practice-note",
            "content": CONTENT,
        },
    )
    check(status == 201, f"期望 201，实际 {status}")
    items = payload.get("items") or []
    check(bool(items) and bool(items[0].get("id")), "没拿到 Evidence ID")
    return items[0]["id"]


def main() -> None:
    id_a1 = ingest(USER_A)
    id_a2 = ingest(USER_A)  # 同用户、同内容
    id_b = ingest(USER_B)   # 不同用户、同内容

    check(id_a1 == id_a2, "同用户同内容应复用同一 ID，却得到两个不同 ID")
    check(id_a1 != id_b, "不同用户不应复用同一条证据 ID")

    print(f"用户 A 第一次：{id_a1}")
    print(f"用户 A 第二次：{id_a2}  （应与第一次相同）")
    print(f"用户 B 同内容：{id_b}  （应与 A 不同）")
    print("OK：去重按「用户 + 规范化文本」生效。")


if __name__ == "__main__":
    main()
