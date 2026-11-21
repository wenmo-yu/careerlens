"""练习 03：同一问题切换 rag / wiki / hybrid 三种检索模式。

对应课程：tutorials/04-retrieval-agent.md
核对：诊断里的 mode / source_kind 随模式变化；不比对回答文本。
运行：python3 examples/tutorials/lesson-03-chat-modes/main.py
"""
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _client import check, prepare_profile, request, tutorial_user  # noqa: E402

USER = tutorial_user("lesson-03-chat-modes")
SLUG = "lesson03-python"
QUESTION = "我做过哪些 Python 项目？"
REQUIRE_QDRANT = os.environ.get("CAREERLENS_TUTORIAL_REQUIRE_QDRANT") == "1"
EXPECTED_SOURCES = {"rag": {"rag"}, "wiki": {"wiki"}, "hybrid": {"rag", "wiki"}}


def compile_wiki(evidence_id: str) -> str:
    _, pages = request("GET", f"/api/v1/wiki?user_id={USER}")
    current = next((page for page in pages if page["slug"] == SLUG), None)
    status, compiled = request(
        "POST", "/api/v1/wiki/compile",
        body={
            "user_id": USER,
            "slug": SLUG,
            "title": "我的 Python 实践",
            "evidence_ids": [evidence_id],
            "base_version": current["version"] if current else None,
        },
    )
    check(status == 201 and bool(compiled["page"]["id"]), "没有拿到 Wiki 页 ID")
    return compiled["page"]["id"]


def wait_for_evidence(evidence_id: str) -> None:
    query = urlencode({"user_id": USER, "query": QUESTION})
    deadline = time.monotonic() + 20
    while (remaining := deadline - time.monotonic()) > 0:
        _, result = request("GET", f"/api/v1/evidence/search?{query}", timeout=min(remaining, 4))
        backend = result["retrieval"].get("backend")
        expected_backend = not REQUIRE_QDRANT or backend == "qdrant"
        if expected_backend and any(hit["evidence_id"] == evidence_id for hit in result["items"]):
            return
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    expected = "Qdrant" if REQUIRE_QDRANT else "证据检索"
    raise AssertionError(f"20 秒内未在{expected}找到刚导入的证据：{evidence_id}")


def ask(mode: str, evidence_id: str, page_id: str) -> None:
    status, payload = request(
        "POST",
        "/api/v1/chat",
        body={"user_id": USER, "message": QUESTION, "mode": mode},
    )
    check(status == 200, f"chat({mode}) 失败：{status}")
    diag = payload["retrieval"]
    hits = payload["evidence"]
    expected = EXPECTED_SOURCES[mode]
    kinds = {hit["source_kind"] for hit in hits}
    check(diag.get("mode") == mode, f"诊断 mode 应为 {mode}，实际为 {diag.get('mode')}")
    check(kinds == expected, f"{mode} 应命中 {sorted(expected)}，实际为 {sorted(kinds)}")
    check(diag.get("source_kinds") == sorted(expected), f"{mode} 诊断与实际来源不一致")
    if "rag" in expected:
        check(any(hit.get("evidence_id") == evidence_id for hit in hits), "缺少原始证据引用")
        if REQUIRE_QDRANT:
            check(diag.get("backend") == "qdrant", f"{mode} 未走 Qdrant 检索")
    if "wiki" in expected:
        check(
            any(hit.get("page_id") == page_id and evidence_id in hit["chunk_refs"] for hit in hits),
            "Wiki 命中无法追溯到本次导入的证据",
        )
    if mode == "hybrid":
        check(diag.get("knowledge_fusion") == "rank_interleave", "混合模式缺少交错融合诊断")
    print(
        f"[{mode}] backend={diag.get('backend', '-')} rag_count={diag['rag_count']} "
        f"wiki_count={diag['wiki_count']} source_kinds={sorted(kinds)}"
    )
    if mode == "hybrid":
        print(f"[hybrid] knowledge_fusion={diag['knowledge_fusion']}")


def main() -> None:
    evidence_id = prepare_profile(USER)
    page_id = compile_wiki(evidence_id)
    wait_for_evidence(evidence_id)
    for mode in EXPECTED_SOURCES:
        ask(mode, evidence_id, page_id)
    print("OK：三种模式都命中预期来源，并能追溯到同一条原始证据。")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(f"失败：{exc}") from None
