from fastapi import APIRouter

from app.api.routes import (
    agent,
    agent_inbox,
    agent_multi,
    agent_roles,
    assessment,
    auth,
    catalog,
    chat,
    connectors,
    evaluation,
    evidence,
    jobs,
    learning,
    observability,
    privacy,
    profile,
    profile_extensions,
    recommendations,
    reports,
    runs,
    wiki,
)

router = APIRouter()
router.include_router(agent.router, tags=["agent"])
router.include_router(agent_multi.router, tags=["agent"])
router.include_router(agent_roles.router, tags=["agent"])
router.include_router(agent_inbox.router, tags=["agent"])
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
router.include_router(runs.router, prefix="/runs", tags=["runs"])
router.include_router(privacy.router, prefix="/privacy", tags=["privacy"])
router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])
router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
router.include_router(learning.router, tags=["learning"])
router.include_router(assessment.router, tags=["assessments"])
router.include_router(profile_extensions.router, tags=["profile-extensions"])

