"""M5 model gateway conformance tests over real HTTP/SSE.

These tests run the production client against ``tools/openai_conformance_server.py``
over a real socket, so chunked framing, line splitting, retry timing and
timeouts are exercised. They are still *not* vendor verification: see the
server docstring.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.runtime.agent import model

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from openai_conformance_server import serve  # noqa: E402


@pytest.fixture(scope="module")
def conformance():
    server, base = serve(0)
    yield base
    server.shutdown()


def settings_for(base: str, **overrides) -> SimpleNamespace:
    values = {
        "ai_base_url": f"{base}/v1",
        "ai_api_key": "conformance-key",
        "agent_model_name": "conformance-model",
        "agent_model_temperature": 0.0,
        "agent_model_max_tokens": 128,
        "agent_model_retries": 2,
        "agent_model_backoff_ms": 1,
        "agent_model_stream_timeout_seconds": 2,
        "ai_input_price_per_million": 0.14,
        "ai_output_price_per_million": 0.28,
        "ai_max_prompt_chars": 10_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def query(base: str, mode: str, *, fail: int = 0, delay: float = 0) -> str:
    """Build ``/v1/{mode}/{fail}/{delay}`` so the client can append /chat/completions."""

    return f"{base}/v1/{mode}/{fail}/{delay}"


async def collect(base_url: str, *, tools: list[dict] | None = None, **overrides) -> list[dict]:
    settings = settings_for(base_url, **overrides)
    events = []
    async for event in model.stream_provider(
        [{"role": "user", "content": "你好"}],
        tools or [],
        provider="openai_compatible",
        settings=settings,
    ):
        events.append(event)
    return events


def text_of(events: list[dict]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "delta")


@pytest.mark.asyncio
async def test_streams_text_and_usage_over_real_socket(conformance):
    events = await collect(f"{conformance}/v1")
    assert text_of(events) == "你好，这是来自一致性服务器的回答。"
    done = events[-1]
    assert done["type"] == "done"
    assert done["stop_reason"] == "completed"
    assert done["usage_known"] is True
    assert done["usage"] == {"input_tokens": 128, "output_tokens": 24}


@pytest.mark.asyncio
async def test_missing_usage_is_marked_unknown_not_zero(conformance):
    events = await collect(query(conformance, "no_usage"))
    done = events[-1]
    assert done["usage_known"] is False
    assert done["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert text_of(events).startswith("你好，")


@pytest.mark.asyncio
async def test_tool_call_fragments_are_assembled(conformance):
    tools = [{"name": "search_evidence", "description": "s", "parameters": {}}]
    events = await collect(query(conformance, "tool"), tools=tools)
    calls = [event for event in events if event["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "search_evidence"
    assert calls[0]["args"] == {"query": "Docker", "limit": 3}
    assert events[-1]["stop_reason"] == "tool_calls"


@pytest.mark.asyncio
async def test_non_whitelisted_tool_is_dropped_with_reason(conformance):
    tools = [{"name": "search_evidence", "description": "s", "parameters": {}}]
    events = await collect(query(conformance, "bad_tool"), tools=tools)
    assert not [event for event in events if event["type"] == "tool_call"]
    assert events[-1]["stop_reason"] == "tool_not_allowed"


@pytest.mark.asyncio
async def test_rate_limit_is_retried_and_then_succeeds(conformance):
    events = await collect(query(conformance, "rate_limit", fail=2))
    assert text_of(events) == "你好，这是来自一致性服务器的回答。"
    assert "error" not in events[-1]


@pytest.mark.asyncio
async def test_persistent_rate_limit_fails_closed(conformance):
    events = await collect(query(conformance, "rate_limit", fail=99))
    done = events[-1]
    assert done["stop_reason"] == "model_unavailable"
    assert done["error"] == "rate_limit"
    assert text_of(events) == ""


@pytest.mark.asyncio
async def test_upstream_error_is_reported_not_raised(conformance):
    events = await collect(query(conformance, "server_error"))
    assert events[-1]["error"] == "upstream_error"
    assert events[-1]["stop_reason"] == "model_unavailable"


@pytest.mark.asyncio
async def test_timeout_is_reported_as_timeout(conformance):
    events = await collect(
        query(conformance, "slow", delay=3),
        agent_model_stream_timeout_seconds=0.5,
        agent_model_retries=0,
    )
    assert events[-1]["error"] == "timeout"


@pytest.mark.asyncio
async def test_missing_api_key_fails_before_any_request(conformance):
    with pytest.raises(ValueError):
        async for _ in model.stream_provider(
            [{"role": "user", "content": "hi"}],
            [],
            provider="openai_compatible",
            settings=settings_for(conformance, ai_api_key=""),
        ):
            pass
