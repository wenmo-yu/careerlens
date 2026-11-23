"""练习 06：亲手让评测指标下降——收藏卡挤掉相关证据（Recall@2: 1 → 0.5）。

对应课程：tutorials/08-advanced/08-2-evaluation.md
需要项目的 Python 环境（pydantic 等依赖，用 backend/.venv），不联网、不调模型。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe examples/tutorials/lesson-06-eval/main.py
    # macOS/Linux: backend/.venv/bin/python ...

它做两件事：对两份最小数据集，各打印 (1) 检索 Top-2 命中了哪些证据，(2) 四项评测指标。
两份数据集只差一条"未标为相关"的收藏卡，其余完全相同。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.evaluation import run_evaluation  # noqa: E402
from app.retrieval.hybrid import hybrid_search  # noqa: E402
from app.schemas.evaluation import EvaluationDataset  # noqa: E402

DATASETS = [
    ("无收藏卡", ROOT / "eval/datasets/recall2-demo.json"),
    ("有收藏卡", ROOT / "eval/datasets/recall2-demo-bookmark.json"),
]
METRICS = ["profile_extraction_f1", "evidence_recall_at_k", "supported_claim_rate", "requirement_matching_f1"]


def main() -> None:
    results = {}
    for label, path in DATASETS:
        ds = EvaluationDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
        metrics, _ = run_evaluation(ds)
        results[label] = metrics

        case = ds.cases[0]
        query = case.retrieval_queries[0]
        records = [e.model_dump() for e in case.evidence]
        top = hybrid_search(query.query, records, limit=ds.recall_k)
        top_ids = [item["evidence_id"] for item in top]
        relevant = set(query.relevant_evidence_ids)
        hits = [i for i in top_ids if i in relevant]

        print(f"=== {label} ===")
        print("  检索 Top-2：", top_ids)
        print(f"  命中相关证据：{hits}（{len(hits)}/{len(relevant)}）")
        print("  四项指标：", {k: round(metrics[k], 4) for k in METRICS})

    r0 = results["无收藏卡"]["evidence_recall_at_k"]
    r1 = results["有收藏卡"]["evidence_recall_at_k"]
    assert abs(r0 - 1.0) < 1e-9, r0
    assert abs(r1 - 0.5) < 1e-9, r1
    print(f"\n结论：只加一条未标为相关的收藏卡，Recall@2 从 {r0} 降到 {r1}。")
    print("OK：两个数据集的指标与预测一致。")


if __name__ == "__main__":
    main()
