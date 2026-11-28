"""End-to-end test of the real CLI process against a stub gateway.

Proves: warm handshake, bind, ACK, streamed deltas, a tool call through the
internal gateway, and a settled message with citations. No database or model
provider is involved in the CLI process itself.
"""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.runtime.agent import capability, tools

BACKEND_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


class StubGateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    model_calls = 0
    auth_headers: list[str] = []
    fail_model = False
    done_error = ""

    def log_message(self, *args):  # silence test output
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        StubGateway.auth_headers.append(self.headers.get("X-Agent-Capability", ""))
        if self.path.endswith("/model/complete"):
            if StubGateway.fail_model:
                self._send(503, b'{"detail": "down"}', "application/json")
                return
            StubGateway.model_calls += 1
            if StubGateway.done_error:
                events = [{
                    "type": "done",
                    "stop_reason": "model_unavailable",
                    "error": StubGateway.done_error,
                    "usage": {},
                }]
                body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
                body += "data: [DONE]\n\n"
                self._send(200, body.encode(), "text/event-stream")
                return
            if StubGateway.model_calls == 1:
                events = [
                    {"type": "tool_call", "id": "call-1", "name": "search_evidence",
                     "args": {"query": "Docker"}},
                    {"type": "done", "stop_reason": "tool_calls", "usage": {}},
                ]
            else:
                events = [
                    {"type": "delta", "text": "final "},
                    {"type": "delta", "text": "answer"},
                    {"type": "done", "stop_reason": "completed", "usage": {"output_tokens": 2}},
                ]
            body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
            body += "data: [DONE]\n\n"
            self._send(200, body.encode(), "text/event-stream")
            return
        if self.path.endswith("/tools/invoke"):
            assert payload["name"] == "search_evidence"
            result = {"items": [{"evidence_id": "e1", "content": "Docker work"}]}
            self._send(200, json.dumps({"ok": True, "result": result}).encode(), "application/json")
            return
        self._send(404, b"{}", "application/json")


def start_stub() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


async def talk(process, frame: dict) -> dict:
    process.stdin.write((json.dumps(frame) + "\n").encode())
    await process.stdin.drain()
    line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
    return json.loads(line)


async def test_cli_warm_bind_runs_a_tool_and_settles():
    StubGateway.model_calls = 0
    StubGateway.auth_headers = []
    StubGateway.fail_model = False
    StubGateway.done_error = ""
    server, base = start_stub()
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=1, runtime_generation=2
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-m",
        "app.runtime.agent.cli",
        "--warm",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BACKEND_ROOT),
    )
    try:
        ready = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=20))
        assert ready["kind"] == "runtime.ready"

        bound = await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-1",
                "method": "runtime.bind",
                "params": {
                    "session_id": "s1",
                    "runtime_generation": 2,
                    "api_base": base,
                    "capability": token,
                    "messages": [{"role": "user", "content": "Docker 证据"}],
                },
            },
        )
        assert bound["ok"] is True

        accepted = await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-2",
                "method": "run.start",
                "params": {"run_id": "r1", "attempt": 1, "runtime_generation": 2},
            },
        )
        assert accepted["result"] == {"accepted": True}

        events = []
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=20)
            frame = json.loads(line)
            events.append(frame)
            if frame.get("kind") == "run.settled":
                break
        kinds = [frame["kind"] for frame in events]
        assert "message.delta" in kinds
        assert "tool.requested" in kinds
        assert "tool.completed" in kinds
        settled = events[-1]["payload"]
        assert settled["stop_reason"] == "completed"
        assert settled["message"]["text"] == "final answer"
        assert settled["message"]["citations"] == [
            {"evidence_id": "e1", "source_name": None, "source_type": None}
        ]
        assert StubGateway.model_calls == 2
        assert all(value == token for value in StubGateway.auth_headers)

        stopped = await talk(
            process,
            {"v": 1, "type": "request", "id": "s-3", "method": "runtime.shutdown", "params": {}},
        )
        assert stopped["result"]["stopping"] is True
        assert await asyncio.wait_for(process.wait(), timeout=10) == 0
    finally:
        server.shutdown()
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_cli_settles_failed_when_gateway_is_down():
    StubGateway.model_calls = 0
    StubGateway.fail_model = True
    server, base = start_stub()
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=1, runtime_generation=2
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-m",
        "app.runtime.agent.cli",
        "--warm",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BACKEND_ROOT),
    )
    try:
        await asyncio.wait_for(process.stdout.readline(), timeout=20)
        await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-1",
                "method": "runtime.bind",
                "params": {
                    "session_id": "s1",
                    "runtime_generation": 2,
                    "api_base": base,
                    "capability": token,
                    "messages": [{"role": "user", "content": "x"}],
                },
            },
        )
        await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-2",
                "method": "run.start",
                "params": {"run_id": "r1", "attempt": 1, "runtime_generation": 2},
            },
        )
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=20)
            frame = json.loads(line)
            if frame.get("kind") == "run.settled":
                break
        assert frame["payload"]["stop_reason"] == "failed"
        assert frame["payload"]["error"] == "model_gateway_failed"
    finally:
        server.shutdown()
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_cli_settles_failed_for_a_model_done_error():
    StubGateway.model_calls = 0
    StubGateway.fail_model = False
    StubGateway.done_error = "rate_limit"
    server, base = start_stub()
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=1, runtime_generation=2
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-m",
        "app.runtime.agent.cli",
        "--warm",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BACKEND_ROOT),
    )
    try:
        await asyncio.wait_for(process.stdout.readline(), timeout=20)
        await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-1",
                "method": "runtime.bind",
                "params": {
                    "session_id": "s1",
                    "runtime_generation": 2,
                    "api_base": base,
                    "capability": token,
                    "messages": [{"role": "user", "content": "x"}],
                },
            },
        )
        await talk(
            process,
            {
                "v": 1,
                "type": "request",
                "id": "s-2",
                "method": "run.start",
                "params": {"run_id": "r1", "attempt": 1, "runtime_generation": 2},
            },
        )
        while True:
            frame = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=20))
            if frame.get("kind") == "run.settled":
                break
        assert frame["payload"]["stop_reason"] == "failed"
        assert frame["payload"]["error"] == "rate_limit"
    finally:
        StubGateway.done_error = ""
        server.shutdown()
        if process.returncode is None:
            process.kill()
            await process.wait()


# --- M5 write-tool approval barrier and recovery -----------------------------


class ApprovalStubGateway(StubGateway):
    model_calls = 0
    tool_bodies: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/model/complete"):
            ApprovalStubGateway.model_calls += 1
            if ApprovalStubGateway.model_calls == 1:
                events = [
                    {
                        "type": "tool_call",
                        "id": "call-write",
                        "name": "save_career_note",
                        "args": {"title": "t", "content": "c"},
                    },
                    {"type": "done", "stop_reason": "tool_calls", "usage": {}},
                ]
            else:
                events = [
                    {"type": "delta", "text": "saved"},
                    {"type": "done", "stop_reason": "completed", "usage": {"output_tokens": 1}},
                ]
            body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
            body += "data: [DONE]\n\n"
            self._send(200, body.encode(), "text/event-stream")
            return
        if self.path.endswith("/tools/invoke"):
            ApprovalStubGateway.tool_bodies.append(payload)
            result = {"artifact_id": "a1", "title": "t", "evidence_count": 0}
            self._send(
                200, json.dumps({"ok": True, "result": result}).encode(), "application/json"
            )
            return
        self._send(404, b"{}", "application/json")


def start_approval_stub() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApprovalStubGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


async def spawn_cli():
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-m",
        "app.runtime.agent.cli",
        "--warm",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BACKEND_ROOT),
    )


async def bind_and_start(process, base, token, *, extra=None):
    ready = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=20))
    assert ready["kind"] == "runtime.ready"
    await talk(
        process,
        {
            "v": 1,
            "type": "request",
            "id": "s-1",
            "method": "runtime.bind",
            "params": {
                "session_id": "s1",
                "runtime_generation": 2,
                "api_base": base,
                "capability": token,
                "messages": [{"role": "user", "content": "写一条笔记"}],
            },
        },
    )
    params = {"run_id": "r1", "attempt": 1, "runtime_generation": 2}
    if extra:
        params.update(extra)
    return await talk(
        process,
        {"v": 1, "type": "request", "id": "s-2", "method": "run.start", "params": params},
    )


async def stop_cli(process):
    await talk(
        process,
        {"v": 1, "type": "request", "id": "s-9", "method": "runtime.shutdown", "params": {}},
    )
    assert await asyncio.wait_for(process.wait(), timeout=10) == 0


async def test_cli_stops_at_approval_and_recovers_only_once():
    ApprovalStubGateway.model_calls = 0
    ApprovalStubGateway.tool_bodies = []
    server, base = start_approval_stub()
    token = capability.issue(
        user_id="u1", session_id="s1", run_id="r1", attempt=1, runtime_generation=2
    )
    digest = tools.digest_args({"title": "t", "content": "c"})
    first = await spawn_cli()
    request = None
    try:
        accepted = await bind_and_start(first, base, token)
        assert accepted["result"] == {"accepted": True}
        events = []
        while True:
            frame = json.loads(await asyncio.wait_for(first.stdout.readline(), timeout=20))
            events.append(frame)
            if frame.get("kind") == "approval.requested":
                break
        assert "run.settled" not in [item["kind"] for item in events]
        request = events[-1]["payload"]
        assert request["invocation_id"] == "call-write"
        assert request["tool"] == "save_career_note"
        assert request["args_digest"] == digest
        assert request["scope"] == "agent.artifact.write"
        assert request["tool_calls"][0]["id"] == "call-write"
        assert request["text"] == "" and request["turn"] == 0
        assert ApprovalStubGateway.tool_bodies == []  # 写工具没有被执行
        await stop_cli(first)
    finally:
        if first.returncode is None:
            first.kill()
            await first.wait()

    second = await spawn_cli()
    try:
        pending_tool = {
            "invocation_id": "call-write",
            "tool": "save_career_note",
            "args": {"title": "t", "content": "c"},
            "args_digest": digest,
            "approval_id": "ap-1",
        }
        pending_turn = {
            "invocation_id": "call-write",
            "tool_calls": request["tool_calls"],
            "text": request["text"],
            "turn": request["turn"],
            "args_digest": digest,
        }
        accepted = await bind_and_start(
            second,
            base,
            token,
            extra={"pending_tool": pending_tool, "pending_turn": pending_turn},
        )
        assert accepted["result"] == {"accepted": True}
        events = []
        while True:
            frame = json.loads(await asyncio.wait_for(second.stdout.readline(), timeout=20))
            events.append(frame)
            if frame.get("kind") == "run.settled":
                break
        kinds = [item["kind"] for item in events]
        assert "approval.requested" not in kinds  # 恢复不再触发审批
        assert kinds.count("tool.completed") == 1
        assert events[-1]["payload"]["stop_reason"] == "completed"
        assert len(ApprovalStubGateway.tool_bodies) == 1
        body = ApprovalStubGateway.tool_bodies[0]
        assert body["invocation_id"] == "call-write"
        assert body["approval_id"] == "ap-1"
        assert body["args_digest"] == digest
        assert body["approved"] is True
        await stop_cli(second)
    finally:
        server.shutdown()
        if second.returncode is None:
            second.kill()
            await second.wait()
