import pytest

from app.llm.provider import ModelUnavailable
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
