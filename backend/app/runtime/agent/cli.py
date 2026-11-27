"""Per-session agent CLI.

The scheduler spawns one process per active session. The process speaks the
frozen Runtime JSONL v1 frames on stdio: stdout carries protocol frames only,
stderr carries logs. It loads no user history at warm-up, receives the session
and capability only in ``runtime.bind``, and reports ACK separately from
``run.settled``.

The CLI never holds provider credentials: model and tool calls go through the
internal gateway with a short-lived capability.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import threading
import urllib.error
import urllib.request
from typing import Any

from app.core.config import get_settings
from app.runtime.agent import model as model_gateway
from app.runtime.agent import tools as tool_registry

MAX_FRAME = 1_048_576
DELTA_BATCH_CHARS = 72
PROTOCOL = 1


def log(message: str, **fields: Any) -> None:
    print(json.dumps({"log": message, **fields}, ensure_ascii=False), file=sys.stderr, flush=True)


def emit(kind: str, payload: dict, *, run: dict | None = None, seq: int = 0) -> None:
    frame = {
        "v": 1,
        "type": "event",
        "kind": kind,
        "payload": payload,
        "local_seq": seq,
        "run_id": (run or {}).get("run_id"),
        "attempt": (run or {}).get("attempt", 0),
        "runtime_generation": (run or {}).get("runtime_generation", 0),
    }
    print(json.dumps(frame, ensure_ascii=False), flush=True)


def respond(request_id: str, *, ok: bool, result: dict | None = None, error: dict | None = None):
    frame = {"v": 1, "type": "response", "id": request_id, "ok": ok}
    if ok:
        frame["result"] = result or {}
    else:
        frame["error"] = error or {"code": "handler_error", "message": "unknown error"}
    print(json.dumps(frame, ensure_ascii=False), flush=True)


class Gateway:
    def __init__(self, base_url: str, capability: str):
        self.base_url = base_url.rstrip("/")
        self.capability = capability

    def _request(self, path: str, body: dict) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Agent-Capability": self.capability,
            },
            method="POST",
        )

    def tool(self, name: str, args: dict) -> dict:
        try:
            with urllib.request.urlopen(
                self._request("/internal/agent/tools/invoke", {"name": name, "args": args}),
                timeout=60,
            ) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read())
            except json.JSONDecodeError:
                return {"ok": False, "code": "gateway_error", "message": f"HTTP {exc.code}"}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "code": "gateway_unreachable", "message": str(exc)}

    async def stream_model(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        """Read the gateway SSE stream and return parsed events (blocking I/O off-loop)."""
        return await asyncio.to_thread(self._stream_model_blocking, messages, tools)

    def _stream_model_blocking(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        events: list[dict] = []
        request = self._request(
            "/internal/agent/model/complete", {"messages": messages, "tools": tools}
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                for raw in response:
                    line = raw.decode("utf-8", "strict").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    events.append(json.loads(payload))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"gateway_http_{exc.code}:{body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"gateway_unreachable:{exc}") from exc
        return events


def _digest(args: dict) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def run_turn(run: dict, messages: list[dict], gateway: Gateway) -> None:
    tools = tool_registry.definitions()
    history = list(messages)
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    seq = 0
    text_parts: list[str] = []
    citations: list[dict] = []
    max_turns = get_settings().agent_max_turns

    for turn_index in range(max_turns):
        try:
            events = await gateway.stream_model(history, tools)
        except Exception as exc:  # provider/gateway failure is a failed turn, not a hang
            log("model.failed", error=type(exc).__name__)
            emit(
                "run.settled",
                {
                    "stop_reason": "failed",
                    "message": {"text": "", "citations": []},
                    "usage": usage_total,
                    "error": "model_gateway_failed",
                },
                run=run,
                seq=seq + 1,
            )
            return
        buffered = ""
        tool_calls: list[dict] = []
        stop_reason = "completed"
        for event in events:
            kind = event.get("type")
            if kind == "delta":
                buffered += str(event.get("text", ""))
                while len(buffered) >= DELTA_BATCH_CHARS:
                    chunk, buffered = buffered[:DELTA_BATCH_CHARS], buffered[DELTA_BATCH_CHARS:]
                    seq += 1
                    text_parts.append(chunk)
                    emit("message.delta", {"text": chunk, "turn": turn_index}, run=run, seq=seq)
            elif kind == "tool_call":
                tool_calls.append(event)
            elif kind == "done":
                stop_reason = str(event.get("stop_reason", stop_reason))
                usage = event.get("usage") or {}
                for key in usage_total:
                    usage_total[key] += int(usage.get(key, 0) or 0)
        if buffered:
            seq += 1
            text_parts.append(buffered)
            emit("message.delta", {"text": buffered, "turn": turn_index}, run=run, seq=seq)

        if not tool_calls:
            break

        history.append(
            {"role": "assistant", "content": "".join(text_parts), "tool_calls": tool_calls}
        )
        seq += 1
        emit(
            "tool.requested",
            {"invocation_ids": [call["id"] for call in tool_calls], "turn": turn_index},
            run=run,
            seq=seq,
        )
        for call in tool_calls:
            result = await asyncio.to_thread(gateway.tool, call["name"], call.get("args") or {})
            ok = bool(result.get("ok", False))
            seq += 1
            emit(
                "tool.completed",
                {
                    "invocation_id": call["id"],
                    "status": "succeeded" if ok else "failed",
                    "tool": call["name"],
                    "args_digest": _digest(call.get("args") or {}),
                    "error": None if ok else result.get("code", "tool_error"),
                },
                run=run,
                seq=seq,
            )
            if not ok:
                emit(
                    "run.settled",
                    {
                        "stop_reason": "failed",
                        "message": {"text": "", "citations": []},
                        "usage": usage_total,
                        "error": result.get("code", "tool_error"),
                    },
                    run=run,
                    seq=seq + 1,
                )
                return
            payload = result.get("result", {})
            for item in payload.get("items", []) or []:
                if item.get("evidence_id"):
                    citations.append(
                        {
                            "evidence_id": item["evidence_id"],
                            "source_name": item.get("source_name"),
                            "source_type": item.get("source_type"),
                        }
                    )
            history.append(
                model_gateway.tool_result_message(call["id"], call["name"], payload)
            )
        # A tool turn produced no user-visible final answer yet; keep looping.
        text_parts = []

    seq += 1
    emit(
        "message.completed",
        {"turn": "final", "text": "".join(text_parts), "citation_count": len(citations)},
        run=run,
        seq=seq,
    )
    seq += 1
    emit(
        "run.settled",
        {
            "stop_reason": "completed",
            "message": {"text": "".join(text_parts), "citations": citations},
            "usage": usage_total,
            "turns": turn_index + 1 if "turn_index" in locals() else 0,
        },
        run=run,
        seq=seq,
    )


async def serve(*, warm: bool) -> int:
    log("cli.start", warm=warm, pid=__import__("os").getpid())
    emit("runtime.ready", {"protocol": PROTOCOL, "warm": warm})
    bound: dict | None = None
    gateway: Gateway | None = None
    task: asyncio.Task | None = None

    def start_task(coro) -> asyncio.Task:
        return asyncio.create_task(coro)

    loop = asyncio.get_running_loop()
    # ProactorEventLoop on Windows has no connect_read_pipe, so read stdin in a
    # thread and hand bytes to the loop. This works on Linux and Windows alike.
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def pump() -> None:
        stream = sys.stdin.buffer
        while True:
            line = stream.readline(MAX_FRAME + 1)
            if not line:
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            loop.call_soon_threadsafe(queue.put_nowait, line)

    threading.Thread(target=pump, name="agent-cli-stdin", daemon=True).start()

    while True:
        line = await queue.get()
        if line is None:
            break
        if len(line) > MAX_FRAME:
            respond(
                "s-0",
                ok=False,
                error={"code": "frame_too_large", "message": "frame too large"},
            )
            return 2
        try:
            frame = json.loads(line.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            respond("s-0", ok=False, error={"code": "invalid_frame", "message": "invalid JSON"})
            continue
        if frame.get("type") != "request":
            continue
        request_id = str(frame.get("id", ""))
        method = frame.get("method")
        params = frame.get("params") or {}

        if method == "runtime.bind":
            bound = {
                "session_id": params.get("session_id"),
                "runtime_generation": params.get("runtime_generation"),
                "api_base": params.get("api_base"),
                "capability": params.get("capability"),
                "messages": params.get("messages") or [],
            }
            gateway = Gateway(bound["api_base"], bound["capability"])
            respond(request_id, ok=True, result={"session_id": bound["session_id"]})
        elif method == "run.start":
            if bound is None or gateway is None:
                respond(
                    request_id,
                    ok=False,
                    error={"code": "not_ready", "message": "bind before run.start"},
                )
                continue
            run = {
                "run_id": params.get("run_id"),
                "attempt": int(params.get("attempt", 1)),
                "runtime_generation": bound["runtime_generation"],
            }
            respond(request_id, ok=True, result={"accepted": True})
            task = start_task(run_turn(run, bound["messages"], gateway))
        elif method == "runtime.ping":
            respond(request_id, ok=True, result={"pong": True, "bound": bound is not None})
        elif method == "run.cancel":
            if task is not None:
                task.cancel()
            respond(request_id, ok=True, result={"cancelled": task is not None})
        elif method == "runtime.shutdown":
            if task is not None:
                task.cancel()
            respond(request_id, ok=True, result={"stopping": True})
            break
        else:
            respond(
                request_id,
                ok=False,
                error={"code": "unknown_method", "message": f"unknown method: {method}"},
            )
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CareerLens agent CLI")
    parser.add_argument("--warm", action="store_true", help="start empty and wait for bind")
    args = parser.parse_args()
    code = asyncio.run(serve(warm=args.warm))
    sys.stdout.flush()
    sys.stderr.flush()
    # The stdin pump thread stays blocked in readline; normal interpreter
    # finalization can fault on Windows while it owns the stdin buffer. The
    # process has already flushed its frames, so exit the process directly.
    import os

    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
