"""OpenAI-compatible conformance server for the agent model gateway.

This is a *test double over real HTTP*: it speaks the wire protocol the gateway
consumes (SSE ``data:`` frames, ``choices[].delta``, ``usage``, ``[DONE]``) and
can inject the failure modes we must handle (429, 5xx, slow responses, missing
usage, partial tool-call fragments).

It exists because ``httpx.MockTransport`` bypasses chunked framing, line
splitting and timeouts. Running the real client against a real socket covers
those code paths.

It is **not** a vendor verification: it cannot prove DeepSeek/OpenAI semantics,
pricing or rate-limit behaviour. Vendor end-to-end remains an open gap.

Manual use::

    python tools/openai_conformance_server.py --port 8123
    AI_BASE_URL=http://127.0.0.1:8123/v1 AGENT_MODEL_PROVIDER=local \\
    AI_API_KEY=conformance AGENT_MODEL_NAME=conformance-model \\
    python -m app.runtime.agent.cli --help

Query modes: ``ok`` (default), ``tool``, ``bad_tool``, ``rate_limit``,
``server_error``, ``slow``, ``no_usage``. The mode is a path segment so the
client can append ``/chat/completions`` normally::

    /v1/chat/completions            -> ok
    /v1/{mode}/chat/completions     -> mode
    /v1/{mode}/{fail}/{delay}/chat/completions

``fail=N`` makes ``rate_limit`` fail the first N requests; ``delay=S`` makes
``slow`` sleep S seconds. ``/stats`` reports request counts.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

TEXT_DELTAS = ["你好，", "这是来自", "一致性服务器的回答。"]
TOOL_ARGS = {"query": "Docker", "limit": 3}


class _State:
    def __init__(self) -> None:
        self.requests = 0
        self.authorization: list[str] = []
        self.lock = threading.Lock()

    def record(self, auth: str | None) -> int:
        with self.lock:
            self.requests += 1
            if auth:
                self.authorization.append(auth)
            return self.requests


def _chunk(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _delta(text: str, finish: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    delta: dict = {}
    if text:
        delta["content"] = text
    if tool_calls:
        delta["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-conformance",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "conformance-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state = _State()

    def log_message(self, *args) -> None:  # keep the test output quiet
        pass

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.startswith("/stats"):
            with self.state.lock:
                body = {
                    "requests": self.state.requests,
                    "authorization": list(self.state.authorization),
                }
            self._json(200, body)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        if parts[-2:] != ["chat", "completions"]:
            self._json(404, {"error": "not found"})
            return
        prefix = parts[:-2]
        mode = prefix[1] if len(prefix) > 1 else "ok"
        fail = int(prefix[2]) if len(prefix) > 2 else 0
        delay = float(prefix[3]) if len(prefix) > 3 else 0.0
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)

        attempt = self.state.record(self.headers.get("Authorization"))
        if mode == "rate_limit" and attempt <= fail:
            self._json(429, {"error": {"type": "rate_limit_exceeded"}})
            return
        if mode == "server_error":
            self._json(500, {"error": {"type": "server_error"}})
            return
        if mode == "slow":
            time.sleep(delay or 5)
            self._json(504, {"error": {"type": "timeout"}})
            return
        if mode == "bad_request":
            self._json(400, {"error": {"type": "invalid_request"}})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            if mode == "tool":
                self._tool_call_stream()
            elif mode == "bad_tool":
                self._tool_call_stream(name="dangerous_shell")
            else:
                for piece in TEXT_DELTAS:
                    self.wfile.write(_chunk(_delta(piece)))
                    self.wfile.flush()
                    time.sleep(0.01)
                self.wfile.write(_chunk(_delta("", finish="stop")))
                if mode != "no_usage":
                    self.wfile.write(
                        _chunk(
                            {
                                "id": "chatcmpl-conformance",
                                "object": "chat.completion.chunk",
                                "usage": {
                                    "prompt_tokens": 128,
                                    "completion_tokens": 24,
                                    "total_tokens": 152,
                                },
                            }
                        )
                    )
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _tool_call_stream(self, name: str = "search_evidence") -> None:
        raw = json.dumps(TOOL_ARGS)
        head, tail = raw[: len(raw) // 2], raw[len(raw) // 2 :]
        self.wfile.write(
            _chunk(
                _delta(
                    "",
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call-conformance",
                            "type": "function",
                            "function": {"name": name, "arguments": head},
                        }
                    ],
                )
            )
        )
        self.wfile.flush()
        self.wfile.write(
            _chunk(
                _delta(
                    "",
                    tool_calls=[{"index": 0, "function": {"arguments": tail}}],
                )
            )
        )
        self.wfile.flush()
        self.wfile.write(_chunk(_delta("", finish="tool_calls")))
        if name != "dangerous_shell":
            self.wfile.write(
                _chunk(
                    {
                        "id": "chatcmpl-conformance",
                        "object": "chat.completion.chunk",
                        "usage": {"prompt_tokens": 64, "completion_tokens": 12},
                    }
                )
            )


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the server on a daemon thread; return it and its base URL."""

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    server, base = serve(args.port)
    print(f"conformance server listening on {base}/v1")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
