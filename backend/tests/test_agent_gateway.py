import json

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.llm.provider import ModelUnavailable
from app.models.agent import AgentApproval, AgentArtifact, AgentToolLedger
from app.models.evidence import Evidence
from app.observability.metrics import get_metrics_store
from app.runtime.agent import capability, model, tools


def test_capability_roundtrip_and_tamper_detection():
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=2, runtime_generation=3
    )
    claim = capability.verify(token)
    assert (claim.user_id, claim.session_id, claim.run_id) == ("u1", "s1", "r1")
    assert claim.attempt == 2 and claim.runtime_generation == 3

    body, signature = token.split(".")
    tampered = body[:-2] + ("AA" if body[-2:] != "AA" else "BB") + "." + signature
    with pytest.raises(capability.CapabilityError):
        capability.verify(tampered)
    with pytest.raises(capability.CapabilityError):
        capability.verify("not-a-token")


def test_capability_expires(monkeypatch):
    monkeypatch.setattr(capability.time, "time", lambda: 1000)
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=1, runtime_generation=1, ttl_seconds=10
    )
    monkeypatch.setattr(capability.time, "time", lambda: 1011)
    with pytest.raises(capability.CapabilityError):
        capability.verify(token)


async def test_tools_reject_unknown_and_model_supplied_identity(session_factory):
    async with session_factory() as session:
        with pytest.raises(tools.ToolRejected) as unknown:
            await tools.invoke(
                session, user_id="u1", name="delete_everything", args={}, run_id="r1"
            )
        assert unknown.value.code == "unknown_tool"
        with pytest.raises(tools.ToolRejected) as identity:
            await tools.invoke(
                session,
                user_id="u1",
                name="search_evidence",
                args={"query": "Docker", "user_id": "someone-else"},
                run_id="r1",
            )
        assert identity.value.code == "identity_in_args"
        with pytest.raises(tools.ToolRejected) as invalid:
            await tools.invoke(
                session, user_id="u1", name="search_evidence", args={"query": ""}, run_id="r1"
            )
        assert invalid.value.code == "invalid_args"


async def test_read_only_tools_return_empty_results_for_new_user(session_factory):
    async with session_factory.begin() as session:
        result = await tools.invoke(
            session,
            user_id="fresh-user",
            name="search_evidence",
            args={"query": "Docker", "limit": 3},
            run_id="r1",
        )
        assert result["items"] == []
        profile = await tools.invoke(
            session, user_id="fresh-user", name="get_profile", args={}, run_id="r1"
        )
        assert profile["items"] == []


def test_demo_model_calls_a_tool_then_cites_evidence():
    first = model.demo_turn([{"role": "user", "content": "Docker 项目证据"}], tools.definitions())
    assert first.stop_reason == "tool_calls"
    assert first.tool_calls[0]["name"] == "search_evidence"
    assert first.tool_calls[0]["args"]["query"] == "Docker"

    tool_message = model.tool_result_message(
        "call-1",
        "search_evidence",
        {"items": [{"evidence_id": "ev-1", "content": "Docker 部署经验"}]},
    )
    second = model.demo_turn(
        [{"role": "user", "content": "Docker 项目证据"}, tool_message], tools.definitions()
    )
    assert "ev-1" in second.text
    assert second.tool_calls == []


def test_demo_model_without_evidence_is_explicit():
    tool_message = model.tool_result_message("call-1", "search_evidence", {"items": []})
    turn = model.demo_turn(
        [{"role": "user", "content": "什么证据"}, tool_message], tools.definitions()
    )
    assert "没有检索到" in turn.text


def test_scripted_model_advances_one_turn_at_a_time():
    script = [
        {"text": "thinking", "tool_calls": [{"id": "c1", "name": "get_profile", "args": {}}]},
        {"text": "final"},
    ]
    first = model.build_turn([], tools.definitions(), provider="scripted", script=script)
    assert first.stop_reason == "tool_calls"
    second = model.build_turn(
        [{"role": "assistant", "content": "x"}],
        tools.definitions(),
        provider="scripted",
        script=script,
    )
    assert second.text == "final"
    third = model.build_turn(
        [{"role": "assistant", "content": "x"}, {"role": "assistant", "content": "y"}],
        tools.definitions(),
        provider="scripted",
        script=script,
    )
    assert third.text == ""


def test_unsupported_provider_and_oversized_prompt_fail_loudly():
    with pytest.raises(ModelUnavailable):
        model.build_turn([], [], provider="unknown")
    with pytest.raises(ValueError):
        model.build_turn(
            [{"role": "user", "content": "x" * 70_000}], [], provider="demo"
        )


async def test_stream_turn_emits_deltas_then_done():
    turn = model.ModelTurn(text="a" * 30, usage={"output_tokens": 1})
    events = [event async for event in model.stream_turn(turn)]
    assert [event["type"] for event in events] == ["delta", "delta", "done"]
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "a" * 30


# --- M5 remote provider tests (no network: httpx.MockTransport) ----------------


@pytest.fixture(autouse=True)
def _clear_metrics():
    get_metrics_store()._calls.clear()
    yield


def _settings(**overrides) -> Settings:
    values = {
        "agent_model_provider": "openai_compatible",
        "ai_base_url": "https://model.test/v1",
        "ai_api_key": "unit-test-key",  # fake key, never a real credential
        "ai_model": "fallback-model",
        "agent_model_name": "agent-model",
        "agent_model_retries": 0,
        "agent_model_backoff_ms": 0,
        "ai_input_price_per_million": 1.0,
        "ai_output_price_per_million": 2.0,
    }
    values.update(overrides)
    return Settings(**values)


def _sse(*chunks: dict, done: bool = True) -> bytes:
    frames = [f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks]
    if done:
        frames.append("data: [DONE]\n\n")
    return "".join(frames).encode()


def _text_chunk(text: str, finish: str | None = None, usage: dict | None = None) -> dict:
    body = {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}
    if usage is not None:
        body["usage"] = usage
    return body


def _fragment(
    index: int,
    *,
    call_id: str | None = None,
    name: str | None = None,
    args: str | None = None,
):
    fragment: dict = {"index": index}
    if call_id is not None:
        fragment["id"] = call_id
    function = {}
    if name is not None:
        function["name"] = name
    if args is not None:
        function["arguments"] = args
    if function:
        fragment["function"] = function
    return fragment


def _tool_chunk(*fragments: dict, finish: str | None = None) -> dict:
    return {
        "choices": [
            {"index": 0, "delta": {"tool_calls": list(fragments)}, "finish_reason": finish}
        ]
    }


async def _collect(
    payload: bytes | type[Exception] | tuple[int, bytes],
    *,
    settings: Settings | None = None,
    tools_list: list[dict] | None = None,
    calls_seen: list[httpx.Request] | None = None,
    count: list[int] | None = None,
) -> list[dict]:
    """Drive stream_provider with a fake transport; payload describes every attempt."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls_seen is not None:
            calls_seen.append(request)
        if count is not None:
            count.append(1)
        if isinstance(payload, tuple):
            status, body = payload
            return httpx.Response(
                status, content=body, headers={"content-type": "text/event-stream"}
            )
        if isinstance(payload, type) and issubclass(payload, Exception):
            raise payload("injected transport failure")
        return httpx.Response(200, content=payload, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        return [
            event
            async for event in model.stream_provider(
                [{"role": "user", "content": "给我 Docker 证据"}],
                tools_list if tools_list is not None else tools.definitions(),
                provider="openai_compatible",
                client=client,
                settings=settings or _settings(),
            )
        ]
    finally:
        await client.aclose()


def test_agent_model_provider_allows_five_values_and_key_validation():
    for value in ("demo", "scripted", "openai_compatible", "deepseek", "local"):
        assert Settings(agent_model_provider=value).agent_model_provider == value
    with pytest.raises(ValidationError):
        Settings(agent_model_provider="bogus")
    Settings(agent_model_provider="demo").validate_agent_model()
    Settings(agent_model_provider="scripted").validate_agent_model()
    with pytest.raises(ValueError):
        Settings(agent_model_provider="deepseek").validate_agent_model()


async def test_stream_provider_demo_and_scripted_stay_compatible():
    messages = [{"role": "user", "content": "Docker 证据"}]
    defs = tools.definitions()
    offline = [event async for event in model.stream_provider(messages, defs, provider="demo")]
    turn = model.build_turn(messages, defs, provider="demo")
    expected = [event async for event in model.stream_turn(turn)]
    assert offline == expected

    script = [{"text": "脚本答复"}, {"text": "完成"}]
    scripted = [
        event
        async for event in model.stream_provider([], defs, provider="scripted", script=script)
    ]
    assert scripted == [
        {"type": "delta", "text": "脚本答复"},
        {
            "type": "done",
            "stop_reason": "completed",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    ]


async def test_remote_text_stream_emits_usage_provider_and_metric():
    body = _sse(
        _text_chunk("你好"),
        _text_chunk("，世界", finish="stop", usage={"prompt_tokens": 7, "completion_tokens": 3}),
    )
    requests: list[httpx.Request] = []
    events = await _collect(body, calls_seen=requests)
    assert [event["type"] for event in events] == ["delta", "delta", "done"]
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "你好，世界"
    done = events[-1]
    assert done["stop_reason"] == "completed"
    assert done["usage"] == {"input_tokens": 7, "output_tokens": 3}
    assert done["usage_known"] is True
    assert done["provider"] == "openai_compatible" and done["model"] == "agent-model"

    sent = json.loads(requests[0].content)
    assert sent["stream"] is True
    assert sent["tool_choice"] == "auto"
    assert "response_format" not in sent  # tools present -> no json_object constraint
    assert sent["tools"][0]["type"] == "function"
    assert sent["temperature"] == 0.1 and sent["max_tokens"] == 2048
    assert requests[0].headers["authorization"] == "Bearer unit-test-key"

    calls = get_metrics_store().calls()
    assert len(calls) == 1
    assert calls[0]["operation"] == "agent.stream_provider"
    assert calls[0]["status"] == "success" and calls[0]["prompt_tokens"] == 7
    assert calls[0]["estimated_cost_usd"] == pytest.approx(13 / 1_000_000)
    assert calls[0]["pricing_configured"] is True
    assert "unit-test-key" not in json.dumps(calls)


async def test_remote_tool_calls_accumulate_before_single_done():
    body = _sse(
        _text_chunk("检索中"),
        _tool_chunk(_fragment(0, call_id="c1", name="search_evidence", args='{"que')),
        _tool_chunk(_fragment(0, args='ry": "Docker", "limit": 3}')),
        _tool_chunk(finish="tool_calls"),
    )
    events = await _collect(body)
    assert [event["type"] for event in events] == ["delta", "tool_call", "done"]
    assert events[1]["id"] == "c1" and events[1]["name"] == "search_evidence"
    assert events[1]["args"] == {"query": "Docker", "limit": 3}
    assert events[2]["stop_reason"] == "tool_calls"


async def test_remote_invalid_tool_json_never_executes_partial_call():
    body = _sse(
        _tool_chunk(
            _fragment(0, call_id="c1", name="search_evidence", args='{"query": "Docker"'),
            finish="tool_calls",
        ),
    )
    events = await _collect(body)
    assert [event["type"] for event in events] == ["done"]
    assert events[0]["stop_reason"] == "invalid_tool_args"
    assert events[0]["error"] == "invalid_tool_args"


async def test_remote_429_retries_then_succeeds():
    body = _sse(_text_chunk("恢复", finish="stop"))
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, content=b'{"error":"slow down"}')
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        events = [
            event
            async for event in model.stream_provider(
                [{"role": "user", "content": "hi"}],
                tools.definitions(),
                provider="openai_compatible",
                client=client,
                settings=_settings(agent_model_retries=2),
            )
        ]
    finally:
        await client.aclose()
    assert len(attempts) == 2
    assert [event["type"] for event in events] == ["delta", "done"]
    assert events[-1]["stop_reason"] == "completed"
    assert get_metrics_store().calls()[0]["status"] == "success"


async def test_remote_retry_exhaustion_yields_explicit_failure():
    count: list[int] = []
    events = await _collect(
        (503, b'{"error":"down"}'), settings=_settings(agent_model_retries=1), count=count
    )
    assert len(count) == 2
    assert [event["type"] for event in events] == ["done"]
    assert events[0]["stop_reason"] == "model_unavailable"
    assert events[0]["error"] == "upstream_error"
    assert events[0]["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert events[0]["usage_known"] is False
    call = get_metrics_store().calls()[0]
    assert call["status"] == "error" and call["error_type"] == "upstream_error"


async def test_remote_missing_usage_is_marked_unknown():
    events = await _collect(_sse(_text_chunk("没有用量", finish="stop")))
    assert events[-1]["usage_known"] is False
    assert events[-1]["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert get_metrics_store().calls()[0]["pricing_configured"] is False


async def test_remote_prompt_budget_and_tool_list_fail_loud():
    # Async generators validate on first iteration, so drive them to completion.
    with pytest.raises(ValueError, match="prompt budget"):
        [
            event
            async for event in model.stream_provider(
                [{"role": "user", "content": "x" * 70_000}],
                [],
                provider="openai_compatible",
                settings=_settings(),
            )
        ]
    with pytest.raises(ValueError, match="non-empty name"):
        [
            event
            async for event in model.stream_provider(
                [{"role": "user", "content": "x"}],
                [{"name": "ok"}, {"name": 7}],
                provider="openai_compatible",
                settings=_settings(),
            )
        ]


async def test_remote_unknown_tool_name_is_not_emitted():
    body = _sse(
        _tool_chunk(
            _fragment(0, call_id="c1", name="delete_everything", args="{}"),
            finish="tool_calls",
        ),
    )
    events = await _collect(body, tools_list=[{"name": "search_evidence", "parameters": {}}])
    assert [event["type"] for event in events] == ["done"]
    assert events[0]["stop_reason"] == "tool_not_allowed"
    assert events[0]["error"] == "tool_not_allowed"


async def test_remote_missing_key_fails_loud_without_network():
    with pytest.raises(ValueError, match="AI_API_KEY"):
        [
            event
            async for event in model.stream_provider(
                [{"role": "user", "content": "x"}],
                [],
                provider="deepseek",
                settings=_settings(ai_api_key=""),
            )
        ]


# --- M5 durable tool ledger tests -------------------------------------------


def _note_args(title="笔记", content="内容", evidence_ids=None):
    args = {"title": title, "content": content}
    if evidence_ids is not None:
        args["evidence_ids"] = evidence_ids
    return args


async def _approved_note(
    session, *, args, user="u1", run="r1", invocation="call-1", status="approved"
):
    record = AgentApproval(
        run_id=run,
        user_id=user,
        invocation_id=invocation,
        tool="save_career_note",
        args_digest=tools.digest_args(args),
        scope="agent.artifact.write",
        status=status,
    )
    session.add(record)
    await session.flush()
    return record


async def _invoke_note(session, *, args, approval, user="u1", run="r1"):
    return await tools.invoke(
        session,
        user_id=user,
        name="save_career_note",
        args=args,
        run_id=run,
        session_id="s1",
        invocation_id=approval.invocation_id,
        approval_id=approval.id,
        approved=approval.status == "approved",
        args_digest=tools.digest_args(args),
    )


async def test_write_tool_requires_an_approval(session_factory):
    args = _note_args()
    async with session_factory.begin() as session:
        with pytest.raises(tools.ToolRejected) as missing:
            await tools.invoke(
                session,
                user_id="u1",
                name="save_career_note",
                args=args,
                run_id="r1",
                session_id="s1",
                invocation_id="call-1",
            )
        assert missing.value.code == "approval_required"
        denied = await _approved_note(session, args=args, status="denied")
        with pytest.raises(tools.ToolRejected) as rejected:
            await _invoke_note(session, args=args, approval=denied)
        assert rejected.value.code == "approval_required"
        count = await session.scalar(select(func.count()).select_from(AgentArtifact))
        assert count == 0


async def test_approved_write_executes_once_and_replay_returns_same_result(session_factory):
    args = _note_args()
    async with session_factory.begin() as session:
        approval = await _approved_note(session, args=args)
        first = await _invoke_note(session, args=args, approval=approval)
        assert first["title"] == "笔记" and first["evidence_count"] == 0
        assert first["artifact_id"]
        second = await _invoke_note(session, args=args, approval=approval)
        assert second == first
        artifacts = list(await session.scalars(select(AgentArtifact)))
        assert len(artifacts) == 1
        assert artifacts[0].title == "笔记"
        assert artifacts[0].run_id == "r1"
        ledger = list(await session.scalars(select(AgentToolLedger)))
        assert len(ledger) == 1
        assert ledger[0].status == "succeeded" and ledger[0].result == first
        assert ledger[0].approval_id == approval.id


async def test_same_invocation_with_a_different_digest_conflicts(session_factory):
    args = _note_args(content="原文")
    async with session_factory.begin() as session:
        approval = await _approved_note(session, args=args)
        await _invoke_note(session, args=args, approval=approval)
    changed = _note_args(content="改写")
    with pytest.raises(tools.ToolRejected) as conflict:
        async with session_factory.begin() as session:
            await tools.invoke(
                session,
                user_id="u1",
                name="save_career_note",
                args=changed,
                run_id="r1",
                session_id="s1",
                invocation_id="call-1",
                approval_id=approval.id,
                approved=True,
                args_digest=tools.digest_args(changed),
            )
    assert conflict.value.code == "tool_ledger_conflict"


async def test_write_rejects_unknown_and_cross_user_evidence(session_factory):
    missing_args = _note_args(evidence_ids=["ev-missing"])
    cross_args = _note_args(evidence_ids=["ev-other"])
    async with session_factory.begin() as session:
        session.add(
            Evidence(
                id="ev-own", user_id="u1", source_type="text", source_name="own", content="c"
            )
        )
        session.add(
            Evidence(
                id="ev-other", user_id="u2", source_type="text", source_name="other", content="c"
            )
        )
        await session.flush()
        missing = await _approved_note(session, args=missing_args)
        cross = await _approved_note(session, args=cross_args, invocation="call-2")
    for args, approval in ((missing_args, missing), (cross_args, cross)):
        with pytest.raises(tools.ToolRejected) as exc:
            async with session_factory.begin() as session:
                await _invoke_note(session, args=args, approval=approval)
        assert exc.value.code == "invalid_args"
    own_args = _note_args(evidence_ids=["ev-own"])
    async with session_factory.begin() as session:
        own = await _approved_note(session, args=own_args, invocation="call-3")
        result = await _invoke_note(session, args=own_args, approval=own)
    assert result["evidence_count"] == 1


async def test_write_rejects_a_mismatched_approval(session_factory):
    args = _note_args()
    async with session_factory.begin() as session:
        approval = await _approved_note(session, args=args, run="another-run")
        with pytest.raises(tools.ToolRejected) as exc:
            await _invoke_note(session, args=args, approval=approval)
        assert exc.value.code == "approval_mismatch"
        assert await session.scalar(select(func.count()).select_from(AgentArtifact)) == 0
