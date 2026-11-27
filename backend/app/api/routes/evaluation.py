from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.evaluation import (
    EvaluationDataset,
    EvaluationRunRead,
    RegressionRequest,
    RegressionResult,
)
from app.security.auth import authorize_ops
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


async def _ops_guard(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Evaluation results and controls are scoped to the instance operator."""
    await authorize_ops(session, authorization=authorization)


@router.post("/run", response_model=EvaluationRunRead)
async def run_dataset(
    payload: EvaluationDataset,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> EvaluationRunRead:
    await _ops_guard(session, authorization)
    return await execute_evaluation(session, payload)


@router.post("/sample", response_model=EvaluationRunRead)
async def run_sample(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> EvaluationRunRead:
    await _ops_guard(session, authorization)
    return await execute_evaluation(session, load_sample_dataset(), origin="sample")


@router.post("/regression", response_model=RegressionResult)
async def run_regression(
    payload: RegressionRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> RegressionResult:
    await _ops_guard(session, authorization)
    record, regression = await execute_regression(
        session, payload.dataset, payload.minimums
    )
    return RegressionResult(run=record, **regression)


@router.post("/regression/sample", response_model=RegressionResult)
async def run_sample_regression(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> RegressionResult:
    await _ops_guard(session, authorization)
    minimums = load_sample_thresholds()
    record, regression = await execute_regression(
        session, load_sample_dataset(), minimums, origin="sample",
    )
    return RegressionResult(run=record, **regression)


@router.post("/regression/benchmark", response_model=RegressionResult)
async def run_dev_benchmark_regression(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> RegressionResult:
    """Run the frozen synthetic development benchmark used by CI and the demo UI."""
    await _ops_guard(session, authorization)
    record, regression = await execute_regression(
        session, load_dev_benchmark(), load_dev_benchmark_thresholds(),
        origin="development_benchmark",
    )
    return RegressionResult(run=record, **regression)


@router.get("/runs", response_model=list[EvaluationRunRead])
async def get_runs(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    authorization: Annotated[str | None, Header()] = None,
) -> list[EvaluationRunRead]:
    await _ops_guard(session, authorization)
    return await list_evaluation_runs(session, limit)
