"""Model Gateway for the agent loop.

The gateway owns the provider choice and any future credentials. The CLI only
receives text deltas and tool intents; it never sees an API key. M3 ships a
deterministic ``demo`` provider so the loop, citations and approvals can be
tested without a network, and a ``scripted`` provider for fault injection.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.llm.provider import ModelUnavailable

MAX_MESSAGES = 40
MAX_CHARS = 60_000


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = "completed"
    usage: dict[str, int] = field(default_factory=dict)


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _tool_payloads(messages: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for message in messages:
        if message.get("role") != "tool":
            continue
        try:
            payloads.append(json.loads(str(message.get("content", "{}"))))
        except json.JSONDecodeError:
            continue
    return payloads


def _query_from(text: str) -> str:
    for token in ("Docker", "FastAPI", "Python", "PostgreSQL", "Kubernetes", "SQL"):
        if token.lower() in text.lower():
            return token
    cleaned = " ".join(text.split())
    return cleaned[:60] or "career evidence"


def demo_turn(messages: list[dict], tools: list[dict]) -> ModelTurn:
    """Deterministic two-step turn: search evidence, then answer with citations."""

    available = {tool["name"] for tool in tools}
    payloads = _tool_payloads(messages)
    if not payloads and "search_evidence" in available:
        return ModelTurn(
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "search_evidence",
                    "args": {"query": _query_from(_last_user_text(messages)), "limit": 5},
                }
            ],
            stop_reason="tool_calls",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    items: list[dict] = []
    for payload in payloads:
        for item in payload.get("items", []) or []:
            if item.get("evidence_id"):
                items.append(item)
    if not items:
        text = "没有检索到可引用的证据；请先导入简历或项目材料后再提问。"
        return ModelTurn(text=text, usage={"input_tokens": 0, "output_tokens": 0})

    lines = [f"基于 {len(items)} 条证据："]
    for item in items[:3]:
        content = " ".join(str(item.get("content", "")).split())[:120]
        lines.append(f"- {content}（证据 {item['evidence_id']}）")
    return ModelTurn(
        text="\n".join(lines),
        usage={"input_tokens": 0, "output_tokens": len(lines)},
    )


def scripted_turn(messages: list[dict], script: list[dict]) -> ModelTurn:
    index = sum(1 for message in messages if message.get("role") == "assistant")
    if index >= len(script):
        return ModelTurn(text="", stop_reason="completed")
    entry = script[index]
    calls = list(entry.get("tool_calls", []))
    default_reason = "tool_calls" if calls else "completed"
    return ModelTurn(
        text=str(entry.get("text", "")),
        tool_calls=calls,
        stop_reason=str(entry.get("stop_reason", default_reason)),
        usage={"input_tokens": 0, "output_tokens": 0},
    )


def build_turn(
    messages: list[dict], tools: list[dict], *, provider: str, script: list[dict] | None = None
) -> ModelTurn:
    if len(messages) > MAX_MESSAGES:
        raise ValueError("Too many messages for one turn")
    if sum(len(str(message.get("content", ""))) for message in messages) > MAX_CHARS:
        raise ValueError("Conversation exceeds the model prompt budget")
    if provider == "demo":
        return demo_turn(messages, tools)
    if provider == "scripted" and script is not None:
        return scripted_turn(messages, script)
    raise ModelUnavailable("unsupported_provider")


async def stream_turn(turn: ModelTurn) -> AsyncIterator[dict]:
    """Emit deltas, then tool intents, then a done marker."""

    for chunk in _chunks(turn.text):
        yield {"type": "delta", "text": chunk}
        await asyncio.sleep(0)
    for call in turn.tool_calls:
        yield {"type": "tool_call", **call}
    yield {"type": "done", "stop_reason": turn.stop_reason, "usage": turn.usage}


def _chunks(text: str, size: int = 24) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def tool_result_message(call_id: str, name: str, payload: dict[str, Any]) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": json.dumps(payload, ensure_ascii=False),
    }
