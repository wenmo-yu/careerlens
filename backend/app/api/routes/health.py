import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.models.access_token import AccessToken
from app.models.account_deletion import DeletionWork
from app.models.evidence import Evidence
from app.models.index_generation import IndexGeneration
from app.models.run import AgentRun
from app.observability.prometheus import render_metrics
from app.retrieval.providers import embedding_fingerprint
from app.retrieval.qdrant_store import IndexIncompatible, collection_phase
from app.retrieval.service import get_qdrant_client

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    checks: dict[str, str] = {}
    has_evidence = False
    try:
        async with asyncio.timeout(2):
            result = await session.execute(select(
                select(Evidence.id).limit(1).scalar_subquery(),
                select(AccessToken.expires_at).limit(0).scalar_subquery(),
                select(AgentRun.lease_until).limit(0).scalar_subquery(),
                select(DeletionWork.id).limit(0).scalar_subquery(),
                select(IndexGeneration.collection).limit(0).scalar_subquery(),
            ))
            has_evidence = result.scalar() is not None
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    settings = get_settings()
    if settings.retrieval_backend != "local":
        headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(
                    f"{settings.qdrant_url.rstrip('/')}/readyz", headers=headers
                )
                response.raise_for_status()
            checks["qdrant"] = "ok"
            phase = await asyncio.to_thread(
                lambda: collection_phase(
                    get_qdrant_client(), settings.qdrant_collection,
                    embedding_fingerprint(settings), settings.embedding_dimension,
                )
            )
            if phase == "building" or (phase is None and has_evidence):
                checks["qdrant"] = "index_not_ready"
        except IndexIncompatible:
            checks["qdrant"] = "index_incompatible"
        except Exception:
            checks["qdrant"] = "unavailable"

    available = checks["database"] == "ok" and (
        settings.retrieval_backend != "qdrant" or checks["qdrant"] == "ok"
    )
    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return JSONResponse(status_code=200 if available else 503, content={
        "status": status, "checks": checks,
    })


@router.get("/metrics", include_in_schema=False)
async def metrics() -> object:
    """Prometheus scrape endpoint.

    Deliberately unauthenticated like the probes: it carries no personal data,
    only request counts and latency histograms. Disable it with
    METRICS_ENABLED=false when the API is exposed directly to the internet.
    """
    if not get_settings().metrics_available:
        raise HTTPException(status_code=404, detail="metrics disabled")
    return render_metrics()
