from fastapi import APIRouter

from app.api.routes import (
    auth,
    chat,
    connectors,
    evaluation,
    evidence,
    jobs,
    observability,
    privacy,
    profile,
    reports,
)

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(evidence.router, prefix="/evidence", tags=["evidence"])
router.include_router(profile.router, prefix="/profiles", tags=["profiles"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
router.include_router(
    observability.router, prefix="/observability", tags=["observability"]
)
router.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
router.include_router(reports.router, prefix="/reports", tags=["reports"])
router.include_router(privacy.router, prefix="/privacy", tags=["privacy"])

