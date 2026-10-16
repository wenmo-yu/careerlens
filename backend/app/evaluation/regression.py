from typing import Any

from app.schemas.evaluation import RegressionThresholds


def evaluate_regression(
    metrics: dict[str, Any], minimums: RegressionThresholds
) -> tuple[str, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    for metric, minimum in minimums.model_dump().items():
        actual = float(metrics.get(metric, 0.0))
        if actual < minimum:
            failures.append(
                {
                    "metric": metric,
                    "actual": actual,
                    "minimum": minimum,
                    "delta": round(actual - minimum, 4),
                }
            )
    return ("failed" if failures else "passed"), failures
