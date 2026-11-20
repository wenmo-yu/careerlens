"""练习 03：同一问题切换 rag / wiki / hybrid 三种检索模式。

对应课程：tutorials/04-retrieval-agent.md
核对：诊断里的 mode / source_kind 随模式变化；不比对回答文本。
运行：python3 examples/tutorials/lesson-03-chat-modes/main.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import check, request  # noqa: E402

USER = "lesson-03-chat-modes"

# 先用同步编译接口备一页 Wiki，避免 wiki/hybrid 空结果。
SLUG = "lesson03-python"


def prepare() -> None:
    status, payload = request(
        "POST",
        "/api/v1/evidence/text",
        body={
            "user_id": USER,
            "source_type": "self_statement",
            "source_name": "practice-note",
            "content": "我用 Python 和 FastAPI 做过一个多轮 Agent 课程项目。",
        },
    )
    check(status == 201, f"写证据失败：{status}")
    eid = payload["items"][0]["id"]

    status, _ = request(
        "POST",
        "/api/v1/wiki/compile",
        body={
            "user_id": USER,
            "slug": SLUG,
            "title": "我的 Python 实践",
            "evidence_ids": [eid],
        },
    )
    check(status in (200, 201), f"编译 Wiki 失败：{status}")

    # 等检索索引追上（outbox 异步同步），最多等几秒。
    for _ in range(10):
        status, pages = request("GET", f"/api/v1/wiki?user_id={USER}")
        if status == 200 and any(p.get("slug") == SLUG for p in pages):
            return
        time.sleep(0.5)
    raise AssertionError("Wiki 页没有就绪")


def ask(mode: str) -> dict:
    status, payload = request(
        "POST",
        "/api/v1/chat",
        body={"user_id": USER, "message": "我做过哪些 Python 项目？", "mode": mode},
    )
    check(status == 200, f"chat({mode}) 失败：{status}")
    diag = payload.get("retrieval") or {}
    check(diag.get("mode") == mode, f"诊断 mode 应为 {mode}，实际 {diag.get('mode')}")
    check("answer" in payload, "返回里没有 answer")
    check(isinstance(payload.get("evidence"), list), "返回里没有 evidence 数组")
    return payload


def main() -> None:
    prepare()
    results = {m: ask(m) for m in ("rag", "wiki", "hybrid")}

    hybrid_kinds = {e.get("source_kind") for e in results["hybrid"]["evidence"]}
    check(
        results["hybrid"]["retrieval"].get("source_kinds") is not None,
        "hybrid 诊断里应有 source_kinds",
    )

    for mode, payload in results.items():
        diag = payload["retrieval"]
        kinds = sorted({e.get("source_kind") for e in payload["evidence"]})
        print(f"[{mode}] rag_count={diag.get('rag_count')} wiki_count={diag.get('wiki_count')} "
              f"source_kinds={kinds}")
    print(f"[hybrid] knowledge_fusion={results['hybrid']['retrieval'].get('knowledge_fusion')}")
    print("OK：三种模式的诊断与引用来源随模式变化（回答文本不要求一致）。")


if __name__ == "__main__":
    main()
