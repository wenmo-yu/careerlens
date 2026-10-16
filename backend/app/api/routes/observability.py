from typing import Annotated

from fastapi import APIRouter, Query

from app.observability import get_metrics_store

router = APIRouter()


@router.get("/summary")
async def observability_summary() -> dict:
    return get_metrics_store().summary()


@router.get("/calls")
async def observability_calls(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    items = get_metrics_store().calls(limit)
    return {"items": items, "count": len(items)}
