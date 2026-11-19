from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.services.job_requirements import extract_requirements_with_fallback
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


class Coordinator:
    def __init__(self, progress: Callable[..., Awaitable[None]]) -> None:
        self._progress = progress
        self._remaining = 2

    async def delegate(self, role: str, inputs: dict) -> dict:
        if self._remaining <= 0:
            raise ValueError("Specialist budget exhausted")
        self._remaining -= 1
        await self._progress(role, "running")
        project, graph = SPECIALISTS[role]
        scoped = project(inputs)
        state = await graph.ainvoke({"inputs": scoped})
        result = state["result"]
        stats = {"fallback": bool(
            result["diagnostics"].get("fallback") or result["diagnostics"].get("fallback_reason")
        )}
        if "citation_count" in result:
            stats["citation_count"] = result["citation_count"]
        await self._progress(role, "succeeded", **stats)
        return result

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
}
