"""Model Gateway for the agent loop.

The gateway owns the provider choice and any future credentials. The CLI only
receives text deltas and tool intents; it never sees an API key. M3 ships a
deterministic ``demo`` provider so the loop, citations and approvals can be
tested without a network, and a ``scripted`` provider for fault injection.
M5 adds an OpenAI-compatible streaming provider; its wire contract is the same
``delta`` / ``tool_call`` / ``done`` event sequence as the offline providers.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.llm.provider import ModelUnavailable
from app.observability.metrics import ModelCallMetric, get_metrics_store, now_iso

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


# --- M5: OpenAI-compatible streaming provider ---------------------------------

_REMOTE_PROVIDERS = {"openai_compatible", "deepseek", "local"}
_RETRYABLE = {"rate_limit", "upstream_error", "timeout", "connection_error"}
_FINISH_REASONS = {"stop": "completed", "tool_calls": "tool_calls", "length": "completed"}


@dataclass(frozen=True)
class _RemoteConfig:
    """Resolved settings snapshot; tolerant of partially injected settings objects."""

    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    retries: int
    backoff_ms: int
    timeout: float
    input_price: float
    output_price: float
    max_prompt_chars: int

    @classmethod
    def from_settings(cls, settings: Any) -> "_RemoteConfig":
        def value(name: str, default: Any) -> Any:
            return getattr(settings, name, default)

        timeout = value("agent_model_stream_timeout_seconds", 0) or value("ai_timeout_seconds", 60)
        return cls(
            base_url=str(value("ai_base_url", "https://api.deepseek.com")).rstrip("/"),
            api_key=str(value("ai_api_key", "")),
            model=str(value("agent_model_name", "") or value("ai_model", "deepseek-flash")),
            temperature=float(value("agent_model_temperature", 0.1)),
            max_tokens=int(value("agent_model_max_tokens", 2048)),
            retries=int(value("agent_model_retries", 2)),
            backoff_ms=int(value("agent_model_backoff_ms", 250)),
            timeout=float(timeout),
            input_price=float(value("ai_input_price_per_million", 0)),
            output_price=float(value("ai_output_price_per_million", 0)),
            max_prompt_chars=min(MAX_CHARS, int(value("ai_max_prompt_chars", MAX_CHARS))),
        )


def _validate_tools(tools: list[dict]) -> None:
    if not isinstance(tools, (list, tuple)):
        raise ValueError("tools must be a list of tool definitions")
    seen: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("Each tool definition must be a dict")
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each tool definition needs a non-empty name")
        if name in seen:
            raise ValueError(f"Duplicate tool name: {name}")
        seen.add(name)
        parameters = tool.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError(f"Tool {name} has an invalid parameters schema")


def _validate_prompt(messages: list[dict], budget: int) -> None:
    if len(messages) > MAX_MESSAGES:
        raise ValueError("Too many messages for one turn")
    if sum(len(str(message.get("content", ""))) for message in messages) > budget:
        raise ValueError("Conversation exceeds the model prompt budget")


def _parse_usage(raw: Any) -> tuple[dict[str, int], bool]:
    if not isinstance(raw, dict) or not raw:
        return {"input_tokens": 0, "output_tokens": 0}, False
    prompt = raw.get("prompt_tokens", raw.get("input_tokens", 0)) or 0
    completion = raw.get("completion_tokens", raw.get("output_tokens", 0)) or 0
    return {"input_tokens": int(prompt), "output_tokens": int(completion)}, True


def _failure_reason(exc: BaseException) -> str:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "rate_limit"
        if 500 <= status < 600:
            return "upstream_error"
        if status in {401, 403}:
            return "authentication"
        return "bad_request"
    if isinstance(exc, httpx.RequestError):
        return "connection_error"
    return "response_invalid"


def _request_payload(cfg: _RemoteConfig, messages: list[dict], tools: list[dict]) -> dict:
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": True,  # httpx streams the response; the API also needs the flag.
        "stream_options": {"include_usage": True},
    }
    if tools:
        # Many compatible endpoints reject response_format together with tools.
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": str(tool.get("description", "")),
                    "parameters": tool.get("parameters") or {},
                },
            }
            for tool in tools
        ]
        payload["tool_choice"] = "auto"
    else:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _consume_frame(
    body: Any, calls: dict[int, dict]
) -> tuple[str, str, dict[str, int] | None]:
    """Fold one SSE payload into streamed text and partial tool calls."""

    if not isinstance(body, dict):
        return "", "", None
    text = ""
    finish = ""
    choices = body.get("choices") or []
    if choices and isinstance(choices[0], dict):
        choice = choices[0]
        delta = choice.get("delta") or {}
        text = str(delta.get("content") or "")
        for fragment in delta.get("tool_calls") or []:
            if not isinstance(fragment, dict):
                continue
            index = int(fragment.get("index", 0) or 0)
            call = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if fragment.get("id"):
                call["id"] = str(fragment["id"])
            function = fragment.get("function") or {}
            if function.get("name"):
                call["name"] = str(function["name"])
            if function.get("arguments"):
                call["arguments"] += str(function["arguments"])
        if choice.get("finish_reason"):
            finish = str(choice["finish_reason"])
    usage, known = _parse_usage(body.get("usage"))
    return text, finish, usage if known else None


def _decode_frame(
    frame: str, calls: dict[int, dict]
) -> tuple[str, str, dict[str, int] | None] | None:
    if frame == "[DONE]":
        return None
    try:
        body = json.loads(frame)
    except json.JSONDecodeError:
        return "", "", None
    return _consume_frame(body, calls)


async def _iter_frames(
    response: httpx.Response, calls: dict[int, dict]
) -> AsyncIterator[tuple[str, str, dict[str, int] | None]]:
    pending: list[str] = []
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if line.startswith(":"):
            continue
        if not line:
            if pending:
                decoded = _decode_frame("".join(pending), calls)
                pending = []
                if decoded is None:
                    return
                yield decoded
            continue
        if line.startswith("data:"):
            pending.append(line[5:].lstrip())
    if pending:
        decoded = _decode_frame("".join(pending), calls)
        if decoded is not None:
            yield decoded


def _finalize_tool_calls(
    calls: dict[int, dict], allowed: set[str]
) -> tuple[list[dict], str | None]:
    """Only emit complete, whitelisted calls; a single failure drops them all."""

    ready: list[dict] = []
    for index in sorted(calls):
        call = calls[index]
        name = call["name"]
        if not name or name not in allowed:
            return [], "tool_not_allowed"
        raw = call["arguments"].strip()
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return [], "invalid_tool_args"
        if not isinstance(args, dict):
            return [], "invalid_tool_args"
        ready.append({"id": call["id"] or f"call-{index}", "name": name, "args": args})
    return ready, None


def _record_agent_metric(
    cfg: _RemoteConfig,
    provider: str,
    status: str,
    started: float,
    usage: dict[str, int],
    usage_known: bool,
    error: str | None,
) -> None:
    priced = usage_known and cfg.input_price > 0 and cfg.output_price > 0
    cost = (
        usage["input_tokens"] * cfg.input_price + usage["output_tokens"] * cfg.output_price
    ) / 1_000_000
    get_metrics_store().record(
        ModelCallMetric(
            operation="agent.stream_provider",
            provider=provider,
            model=cfg.model,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            prompt_tokens=usage["input_tokens"],
            completion_tokens=usage["output_tokens"],
            estimated_cost_usd=round(cost, 8),
            error_type=error,
            created_at=now_iso(),
            pricing_configured=priced,
        )
    )


async def stream_provider(
    messages: list[dict],
    tools: list[dict],
    *,
    provider: str,
    script: list[dict] | None = None,
    client: httpx.AsyncClient | None = None,
    settings: Any = None,
) -> AsyncIterator[dict]:
    """Yield model events for the agent loop.

    ``demo`` and ``scripted`` delegate to ``build_turn`` + ``stream_turn`` so
    their event shape stays byte-for-byte compatible with M3. Remote providers
    stream SSE from ``{base_url}/chat/completions`` and emit the same three
    event kinds plus ``usage_known``/``provider``/``model`` on ``done``.
    """

    if provider in {"demo", "scripted"}:
        turn = build_turn(messages, tools, provider=provider, script=script)
        async for event in stream_turn(turn):
            yield event
        return

    if provider not in _REMOTE_PROVIDERS:
        raise ModelUnavailable("unsupported_provider")

    cfg = _RemoteConfig.from_settings(settings or get_settings())
    _validate_tools(tools)
    _validate_prompt(messages, cfg.max_prompt_chars)
    if not cfg.api_key.strip() or cfg.api_key.startswith("replace-with"):
        raise ValueError("AGENT_MODEL_PROVIDER requires a configured AI_API_KEY")
    if not cfg.base_url.startswith(("https://", "http://")):
        raise ValueError("Agent model requires an HTTP(S) AI_BASE_URL")
    if not cfg.model.strip():
        raise ValueError("Agent model requires AGENT_MODEL_NAME or AI_MODEL")

    payload = _request_payload(cfg, messages, tools)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
    allowed = {tool["name"] for tool in tools}
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=cfg.timeout)

    started = time.perf_counter()
    usage = {"input_tokens": 0, "output_tokens": 0}
    usage_known = False
    status = "error"
    failure: str | None = None
    done_error: str | None = None
    stop_reason = "completed"
    emitted = False
    try:
        for attempt in range(cfg.retries + 1):
            if attempt:
                await asyncio.sleep(cfg.backoff_ms / 1000 * 2 ** (attempt - 1))
            try:
                async with client.stream(
                    "POST",
                    f"{cfg.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()

                    calls: dict[int, dict] = {}
                    finish_reason = ""

                    async for text, finish, frame_usage in _iter_frames(response, calls):
                        if text:
                            emitted = True
                            yield {"type": "delta", "text": text}
                        if finish:
                            finish_reason = finish
                        if frame_usage is not None:
                            usage, usage_known = frame_usage, True

                ready, tool_error = _finalize_tool_calls(calls, allowed)
                if tool_error:
                    stop_reason = tool_error
                    done_error = tool_error
                elif ready:
                    stop_reason = "tool_calls"
                    for call in ready:
                        yield {"type": "tool_call", **call}
                else:
                    stop_reason = _FINISH_REASONS.get(finish_reason, finish_reason or "completed")
                status = "success"
                failure = None
                break
            except (
                httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError,
                AttributeError, IndexError,
            ) as exc:
                failure = _failure_reason(exc)
                status = "error"
                if failure in _RETRYABLE and not emitted and attempt < cfg.retries:
                    continue
                stop_reason = "model_unavailable"
                done_error = failure
                break

        done = {
            "type": "done",
            "stop_reason": stop_reason,
            "usage": usage,
            "usage_known": usage_known,
            "provider": provider,
            "model": cfg.model,
        }
        if done_error:
            done["error"] = done_error
        yield done
    finally:
        if owns_client:
            await client.aclose()

    _record_agent_metric(cfg, provider, status, started, usage, usage_known, failure)
