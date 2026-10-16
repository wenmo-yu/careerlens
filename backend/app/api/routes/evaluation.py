from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.evaluation import (
    EvaluationDataset,
    EvaluationRunRead,
    RegressionRequest,
    RegressionResult,
)
from app.services.evaluation import (
    execute_evaluation,
    execute_regression,
    list_evaluation_runs,
    load_dev_benchmark,
    load_dev_benchmark_thresholds,
    load_sample_dataset,
    load_sample_thresholds,
)

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/run", response_model=EvaluationRunRead)
async def run_dataset(payload: EvaluationDataset, session: Session) -> EvaluationRunRead:
    return await execute_evaluation(session, payload)


@router.post("/sample", response_model=EvaluationRunRead)
async def run_sample(session: Session) -> EvaluationRunRead:
    return await execute_evaluation(session, load_sample_dataset())


@router.post("/regression", response_model=RegressionResult)
async def run_regression(payload: RegressionRequest, session: Session) -> RegressionResult:
    record, regression = await execute_regression(
        session, payload.dataset, payload.minimums
    )
    return RegressionResult(run=record, **regression)


@router.post("/regression/sample", response_model=RegressionResult)
async def run_sample_regression(session: Session) -> RegressionResult:
    minimums = load_sample_thresholds()
    record, regression = await execute_regression(
        session, load_sample_dataset(), minimums
    )
    return RegressionResult(run=record, **regression)


@router.post("/regression/benchmark", response_model=RegressionResult)
async def run_dev_benchmark_regression(session: Session) -> RegressionResult:
    """Run the frozen synthetic development benchmark used by CI and the demo UI."""
    record, regression = await execute_regression(
        session, load_dev_benchmark(), load_dev_benchmark_thresholds()
    )
    return RegressionResult(run=record, **regression)


@router.get("/runs", response_model=list[EvaluationRunRead])
async def get_runs(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[EvaluationRunRead]:
    return await list_evaluation_runs(session, limit)
