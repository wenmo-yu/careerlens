from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.career_report import CareerReport
from app.schemas.report import CareerReportGenerateRequest, CareerReportRead
from app.security import authorize_user
from app.services.reports import generate_report, list_reports

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=CareerReportRead, status_code=201)
async def create_report(
    payload: CareerReportGenerateRequest,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> CareerReportRead:
    await authorize_user(
        session,
        user_id=payload.user_id,
        authorization=authorization,
        required_scope="write",
    )
    try:
        return await generate_report(session, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[CareerReportRead])
async def get_reports(
    user_id: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    authorization: Annotated[str | None, Header()] = None,
) -> list[CareerReportRead]:
    await authorize_user(
        session, user_id=user_id, authorization=authorization, required_scope="read"
    )
    return await list_reports(session, user_id=user_id, limit=limit)


async def _authorized_report(
    report_id: str, session: AsyncSession, authorization: str | None
) -> CareerReport:
    report = await session.get(CareerReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Career report not found")
    await authorize_user(
        session,
        user_id=report.user_id,
        authorization=authorization,
        required_scope="read",
    )
    return report


@router.get("/{report_id}/markdown")
async def download_markdown(
    report_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    report = await _authorized_report(report_id, session, authorization)
    return Response(
        content=report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="careerlens-report-v{report.version}.md"'
        },
    )


@router.get("/{report_id}", response_model=CareerReportRead)
async def get_report(
    report_id: str,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> CareerReportRead:
    return await _authorized_report(report_id, session, authorization)
