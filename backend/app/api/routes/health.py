import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.observability.prometheus import render_metrics

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.qdrant_url.rstrip('/')}/readyz")
            response.raise_for_status()
        checks["qdrant"] = "ok"
    except (httpx.HTTPError, OSError):
        checks["qdrant"] = "unavailable"

    ready = all(value == "ok" for value in checks.values())
    status = "ok" if ready else "degraded"
    payload = {"status": status, "checks": checks}
    # A degraded readiness probe must be an HTTP failure, otherwise orchestrators
    # (Compose/Kubernetes) keep sending traffic to an instance with broken deps.
    return JSONResponse(status_code=200 if ready else 503, content=payload)



@router.get("/metrics", include_in_schema=False)
async def metrics() -> object:
    """Prometheus scrape endpoint.

    Deliberately unauthenticated like the probes: it carries no personal data,
    only request counts and latency histograms. Disable it with
    METRICS_ENABLED=false when the API is exposed directly to the internet.
    """
    if not get_settings().metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    return render_metrics()
