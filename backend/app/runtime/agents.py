import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.services.job_requirements import extract_requirements_with_fallback
from app.services.recommendation import recommend_courses
from app.services.reports import _generate_narrative
from app.wiki.compiler import prepare_page


class SourceExcerpt(BaseModel):
    evidence_id: str
    content: str = Field(max_length=250_000)


class WikiTask(BaseModel):
    title: str
    sources: list[SourceExcerpt] = Field(min_length=1, max_length=50)


class TaskSummary(BaseModel):
    role: str
    citation_count: int = Field(ge=0)
    fallback: bool = False


class TaskState(TypedDict, total=False):
    inputs: dict
    result: dict


class RequirementsTask(BaseModel):
    jd_text: str = Field(min_length=10, max_length=40_000)


class VerificationTask(BaseModel):
    allowed_ids: list[str]
    citation_ids: list[str]


def specialist(call: Callable[[dict], Awaitable[dict]]):
    async def perform(state: TaskState) -> dict:
        return {"result": await call(state["inputs"])}

    graph = StateGraph(TaskState)
    graph.add_node("perform", perform)
    graph.add_edge(START, "perform")
    graph.add_edge("perform", END)
    return graph.compile()


async def requirements_task(inputs: dict) -> dict:
    requirements, diagnostics = await extract_requirements_with_fallback(inputs["jd_text"])
    return {"requirements": requirements[:100], "diagnostics": diagnostics}


async def wiki_task(inputs: dict) -> dict:
    task = WikiTask.model_validate(inputs)
    values, refs, diagnostics = await prepare_page(
        task.title, [item.model_dump() for item in task.sources]
    )
    if len(values["content"]) > 260_000 or len(values["summary"] or "") > 4_000:
        raise ValueError("Wiki candidate exceeds the result limit")
    return {"values": values, "refs": refs, "diagnostics": diagnostics}


async def report_task(inputs: dict) -> dict:
    narrative, diagnostics = await _generate_narrative(inputs, set(inputs["evidence_ids"]))
    if any(
        len(narrative[field]) > 4000 for field in ("executive_summary", "interview_pitch")
    ) or len(narrative["action_suggestions"]) > 20 or any(
        len(action) > 1200 for action in narrative["action_suggestions"]
    ):
        raise ValueError("Report candidate exceeds the result limit")
    return {"narrative": narrative, "diagnostics": diagnostics}


async def verification_task(inputs: dict) -> dict:
    task = VerificationTask.model_validate(inputs)
    refs = set(task.citation_ids)
    if not refs <= set(task.allowed_ids):
        raise ValueError("Citations are outside the task's evidence scope")
    return {"citation_count": len(refs), "diagnostics": {}}


class DraftProjection(BaseModel):
    """HY4-E: specialists see only a whitelist, never raw uploads or secrets."""

    skill_names: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=500)
    enabled_dimensions: list[str] = Field(default_factory=list, max_length=50)
    gaps: list[str] = Field(default_factory=list, max_length=100)
    weekly_hours: int = Field(default=8, ge=1, le=80)


async def profile_cartographer_task(inputs: dict) -> dict:
    """Draft dimension mapping only; never writes a profile table."""
    task = DraftProjection.model_validate(inputs)
    return {
        "draft": {
            "skill_names": task.skill_names,
            "evidence_ids": task.evidence_ids,
            "dimensions": task.enabled_dimensions,
        },
        "diagnostics": {"readonly": True, "fallback": False},
    }


async def role_scout_task(inputs: dict) -> dict:
    """Read-only role suggestions from already-projected skill names."""
    task = DraftProjection.model_validate(inputs)
    suggestions = [
        {"name": name, "evidence_ids": task.evidence_ids[:10]}
        for name in task.skill_names[:10]
    ]
    return {
        "suggestions": suggestions,
        "diagnostics": {"readonly": True, "fallback": False},
    }


async def curriculum_planner_task(inputs: dict) -> dict:
    """Read-only course drafts; URLs come from the local catalog."""
    task = DraftProjection.model_validate(inputs)
    drafts = []
    for skill in task.gaps[:4]:
        drafts.extend(recommend_courses(skill, weekly_hours=task.weekly_hours, limit=2))
    return {
        "drafts": drafts,
        "diagnostics": {"readonly": True, "fallback": False},
    }


class Coordinator:
    """Serial-by-default specialist dispatcher with an explicit call budget.

    HY4-E: budget is now configurable (the old hard-coded 2 is kept as the
    default so existing operations behave identically). ``delegate`` emits a
    failed step on error so the SSE view never shows a step stuck at running.
    ``delegate_many`` is opt-in for genuinely independent read-only roles and
    only safe after the event sequence was moved to an atomic SQL increment.
    """

    def __init__(
        self, progress: Callable[..., Awaitable[None]], *, budget: int = 2
    ) -> None:
        if budget < 1:
            raise ValueError("Coordinator budget must be at least 1")
        self._progress = progress
        self._remaining = budget

    def _stats(self, result: dict, started: float) -> dict:
        diagnostics = result.get("diagnostics") or {}
        stats = {
            "fallback": bool(
                diagnostics.get("fallback") or diagnostics.get("fallback_reason")
            ),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        if "citation_count" in result:
            stats["citation_count"] = result["citation_count"]
        return stats

    async def _run_role(self, role: str, inputs: dict) -> dict:
        """Execute one specialist without touching the budget counter."""
        await self._progress(role, "running")
        started = time.perf_counter()
        try:
            project, graph = SPECIALISTS[role]
            scoped = project(inputs)
            state = await graph.ainvoke({"inputs": scoped})
            result = state["result"]
        except Exception as exc:
            # Without a terminal event the UI shows "running" forever.
            await self._progress(
                role, "failed", error_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            raise
        await self._progress(role, "succeeded", **self._stats(result, started))
        return result

    async def delegate(self, role: str, inputs: dict) -> dict:
        if self._remaining <= 0:
            raise ValueError("Specialist budget exhausted")
        if role not in SPECIALISTS:
            raise ValueError(f"Unknown specialist: {role}")
        self._remaining -= 1
        return await self._run_role(role, inputs)

    async def delegate_many(self, roles: list[str], inputs: dict) -> dict[str, dict]:
        """Run independent read-only specialists concurrently.

        All roles receive the same projected input dict. A failure in any role
        propagates so the caller can fail/retry the whole run; partial results
        are never committed on their own. Budget is charged once per role up
        front, then ``_run_role`` is used so it is not charged twice.
        """
        if not roles:
            return {}
        if len(roles) > self._remaining:
            raise ValueError("Specialist budget exhausted")
        for role in roles:
            if role not in SPECIALISTS:
                raise ValueError(f"Unknown specialist: {role}")
        self._remaining -= len(roles)
        results = await asyncio.gather(
            *(self._run_role(role, inputs) for role in roles),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return dict(zip(roles, results, strict=True))

    async def verify(self, allowed: set[str], refs: list[str]) -> TaskSummary:
        role = "evidence_verifier"
        result = await self.delegate(role, {"allowed_ids": sorted(allowed), "citation_ids": refs})
        return TaskSummary(role=role, citation_count=result["citation_count"])


def report_projection(inputs: dict) -> dict:
    keys = (
        "target_role", "score", "summary", "skills", "matches", "gaps",
        "learning_path", "actions", "evidence_ids",
    )
    return {key: inputs[key] for key in keys}


SPECIALISTS = {
    "requirement_analyst": (
        lambda inputs: RequirementsTask.model_validate(inputs).model_dump(),
        specialist(requirements_task),
    ),
    "wiki_curator": (lambda inputs: WikiTask.model_validate(inputs).model_dump(),
                     specialist(wiki_task)),
    "report_writer": (report_projection, specialist(report_task)),
    "evidence_verifier": (lambda inputs: VerificationTask.model_validate(inputs).model_dump(),
                          specialist(verification_task)),
    "profile_cartographer": (lambda inputs: DraftProjection.model_validate(inputs).model_dump(),
                             specialist(profile_cartographer_task)),
    "role_scout": (lambda inputs: DraftProjection.model_validate(inputs).model_dump(),
                   specialist(role_scout_task)),
    "curriculum_planner": (lambda inputs: DraftProjection.model_validate(inputs).model_dump(),
                           specialist(curriculum_planner_task)),
}

# Roles added in HY4-E are read-only drafts. They may be run in parallel only
# when their inputs are independent; they never write business tables.
PARALLEL_SAFE_ROLES = frozenset({"role_scout", "curriculum_planner"})
