import json
import uuid
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.llm import get_llm_provider
from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.retrieval.service import search_evidence


class CareerState(TypedDict, total=False):
    message: str
    user_id: str
    intent: str
    profile: list[dict]
    evidence_records: list[dict]
    retrieved_evidence: list[dict]
    retrieval_diagnostics: dict
    answer: str
    model_diagnostics: dict


def understand_intent(state: CareerState) -> dict:
    message = state["message"].lower()
    if any(word in message for word in ("为什么", "证据", "依据")):
        intent = "evidence_explanation"
    elif any(word in message for word in ("缺口", "还差", "学习")):
        intent = "skill_gap"
    elif any(word in message for word in ("适合", "方向", "岗位")):
        intent = "career_direction"
    else:
        intent = "profile_question"
    return {"intent": intent}


async def retrieve_evidence(state: CareerState) -> dict:
    results, diagnostics = await search_evidence(
        user_id=state["user_id"],
        query=state["message"],
        evidence=state.get("evidence_records", []),
        limit=5,
    )
    return {
        "retrieved_evidence": results,
        "retrieval_diagnostics": diagnostics,
    }


def _fallback_answer(state: CareerState) -> str:
    profile = state.get("profile", [])
    evidence = state.get("retrieved_evidence", [])
    top_skills = [item for item in profile if item["category"] == "skill"][:5]
    skill_text = "、".join(item["name"] for item in top_skills) or "尚未形成足够画像"
    citations = "、".join(item["evidence_id"] for item in evidence) or "无直接证据"
    intent = state["intent"]
    if intent == "career_direction":
        answer = (
            f"从当前可验证画像看，你的突出能力是 {skill_text}。"
            "建议优先结合目标 JD 做逐项匹配，而不是只看岗位名称。"
        )
    elif intent == "skill_gap":
        answer = "请先提交目标 JD；能力缺口必须由 JD 要求与当前画像逐项比较。"
    elif intent == "evidence_explanation":
        answer = f"本次回答检索到的主要证据为：{citations}。你可以按 Evidence ID 回看原文。"
    else:
        answer = f"当前画像中置信度较高的技能包括：{skill_text}。"
    return answer


async def compose_answer(state: CareerState) -> dict:
    fallback = _fallback_answer(state)
    provider = get_llm_provider()
    if provider.diagnostics["provider"] == "demo":
        return {"answer": fallback, "model_diagnostics": provider.diagnostics}
    context = {
        "question": state["message"],
        "intent": state["intent"],
        "profile": state.get("profile", []),
        "evidence": state.get("retrieved_evidence", []),
    }
    schema = {
        "type": "object",
        "required": ["answer", "cited_evidence_ids"],
        "properties": {
            "answer": {"type": "string"},
            "cited_evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
    }
    try:
        generated = await provider.generate_json(
            system_prompt=(
                "你是证据优先的职业顾问。只能基于给出的画像和证据回答；区分已证实、部分支持"
                "和缺口。不得捏造经历。结论后用 [Evidence: ID] 标注引用。"
            ),
            user_prompt=json.dumps(context, ensure_ascii=False),
            schema=schema,
            operation="career_chat",
        )
        answer = str(generated["answer"]).strip()
        allowed = {item["evidence_id"] for item in state.get("retrieved_evidence", [])}
        cited = [item for item in generated.get("cited_evidence_ids", []) if item in allowed]
        suffix = " ".join(f"[Evidence: {item}]" for item in cited if item not in answer)
        return {
            "answer": f"{answer} {suffix}".strip(),
            "model_diagnostics": provider.diagnostics,
        }
    except Exception as exc:
        return {
            "answer": fallback,
            "model_diagnostics": {
                **provider.diagnostics,
                "fallback": True,
                "reason": type(exc).__name__,
            },
        }


builder = StateGraph(CareerState)
builder.add_node("understand_intent", understand_intent)
builder.add_node("retrieve_evidence", retrieve_evidence)
builder.add_node("compose_answer", compose_answer)
builder.add_edge(START, "understand_intent")
builder.add_edge("understand_intent", "retrieve_evidence")
builder.add_edge("retrieve_evidence", "compose_answer")
builder.add_edge("compose_answer", END)
career_graph = builder.compile(checkpointer=InMemorySaver())


def configure_career_graph(checkpointer: object) -> None:
    global career_graph
    career_graph = builder.compile(checkpointer=checkpointer)


async def run_career_graph(
    *,
    user_id: str,
    message: str,
    profile: list[ProfileItem],
    evidence: list[Evidence],
    thread_id: str | None,
) -> dict:
    selected_thread = thread_id or str(uuid.uuid4())
    state = await career_graph.ainvoke(
        {
            "message": message,
            "user_id": user_id,
            "profile": [
                {
                    "category": item.category,
                    "name": item.name,
                    "confidence": item.confidence,
                    "evidence_ids": item.evidence_ids,
                }
                for item in profile
            ],
            "evidence_records": [
                {
                    "id": item.id,
                    "source_type": item.source_type,
                    "source_name": item.source_name,
                    "content": item.content,
                }
                for item in evidence
            ],
        },
        {"configurable": {"thread_id": selected_thread}},
    )
    return {"thread_id": selected_thread, **state}


async def delete_career_threads(thread_ids: list[str]) -> dict:
    checkpointer = career_graph.checkpointer
    if checkpointer is None or not hasattr(checkpointer, "adelete_thread"):
        return {"status": "unavailable", "deleted": 0}
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)
    return {"status": "deleted", "deleted": len(thread_ids)}
