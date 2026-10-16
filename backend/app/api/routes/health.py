import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory

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

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": status, "checks": checks}

