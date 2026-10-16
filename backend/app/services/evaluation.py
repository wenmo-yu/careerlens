import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation import evaluate_regression, run_evaluation
from app.models.evaluation import EvaluationRun
from app.schemas.evaluation import EvaluationDataset, RegressionThresholds


def load_sample_dataset() -> EvaluationDataset:
    path = Path(__file__).parents[1] / "evaluation" / "sample_dataset.json"
    return EvaluationDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_sample_thresholds() -> RegressionThresholds:
    path = Path(__file__).parents[1] / "evaluation" / "sample_baseline.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RegressionThresholds.model_validate(payload["minimums"])


def load_dev_benchmark() -> EvaluationDataset:
    path = Path(__file__).parents[1] / "evaluation" / "dev_benchmark_v2.json"
    return EvaluationDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_dev_benchmark_thresholds() -> RegressionThresholds:
    path = Path(__file__).parents[1] / "evaluation" / "dev_benchmark_baseline_v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RegressionThresholds.model_validate(payload["minimums"])


async def execute_evaluation(
    session: AsyncSession,
    dataset: EvaluationDataset,
    minimums: RegressionThresholds | None = None,
) -> EvaluationRun:
    metrics, details = run_evaluation(dataset)
    if minimums is not None:
        status, failures = evaluate_regression(metrics, minimums)
        details["regression"] = {
            "status": status,
            "minimums": minimums.model_dump(),
            "failures": failures,
        }
    record = EvaluationRun(
        dataset_name=dataset.name,
        profile_extraction_f1=metrics["profile_extraction_f1"],
        evidence_recall_at_k=metrics["evidence_recall_at_k"],
        supported_claim_rate=metrics["supported_claim_rate"],
        requirement_matching_f1=metrics["requirement_matching_f1"],
        metrics=metrics,
        details=details,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def execute_regression(
    session: AsyncSession,
    dataset: EvaluationDataset,
    minimums: RegressionThresholds,
) -> tuple[EvaluationRun, dict]:
    record = await execute_evaluation(session, dataset, minimums)
    return record, record.details["regression"]


async def list_evaluation_runs(
    session: AsyncSession, limit: int = 20
) -> list[EvaluationRun]:
    result = await session.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit)
    )
    return list(result)
