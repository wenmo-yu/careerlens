import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.evaluation import evaluate_regression, run_evaluation
from app.schemas.evaluation import EvaluationDataset, RegressionThresholds


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CareerLens regression gate")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = EvaluationDataset.model_validate(_load_json(args.dataset))
    baseline = _load_json(args.baseline)
    expected_dataset = baseline.get("dataset")
    if expected_dataset and expected_dataset != dataset.name:
        raise ValueError(
            f"Baseline targets {expected_dataset!r}, but dataset is {dataset.name!r}"
        )
    minimums = RegressionThresholds.model_validate(baseline["minimums"])
    metrics, _ = run_evaluation(dataset)
    status, failures = evaluate_regression(metrics, minimums)
    result = {
        "status": status,
        "dataset": dataset.name,
        "metrics": metrics,
        "minimums": minimums.model_dump(),
        "failures": failures,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
