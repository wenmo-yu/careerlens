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

from app.runtime.agent import capability

BACKEND_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


class StubGateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    model_calls = 0
    auth_headers: list[str] = []
    fail_model = False

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
