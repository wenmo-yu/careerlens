"""Standalone fake agent CLI used by scheduler tests.

It speaks the same JSONL frames as the real CLI but needs no database or HTTP.
Modes are selected with FAKE_CLI_MODE: normal, crash_first, stale_generation,
slow.
"""

import json
import os
import sys
import time


def emit(kind, payload, run, seq):
    print(
        json.dumps(
            {
                "v": 1,
                "type": "event",
                "kind": kind,
                "payload": payload,
                "local_seq": seq,
                "run_id": run["run_id"],
                "attempt": run["attempt"],
                "runtime_generation": run["runtime_generation"],
            }
        ),
        flush=True,
    )


def respond(request_id, result):
    print(
        json.dumps({"v": 1, "type": "response", "id": request_id, "ok": True, "result": result}),
        flush=True,
    )


def main() -> int:
    mode = os.environ.get("FAKE_CLI_MODE", "normal")
    marker = os.environ.get("FAKE_CLI_MARKER", "")
    print(
        json.dumps({"v": 1, "type": "event", "kind": "runtime.ready", "payload": {"protocol": 1}}),
        flush=True,
    )
    generation = 0
    run = None
    for line in sys.stdin:
        frame = json.loads(line)
        if frame.get("type") != "request":
            continue
        request_id = frame["id"]
        method = frame["method"]
        params = frame.get("params") or {}
        if method == "runtime.bind":
            generation = int(params.get("runtime_generation", 0))
            respond(request_id, {"session_id": params.get("session_id")})
        elif method == "run.start":
            run = {
                "run_id": params["run_id"],
                "attempt": int(params.get("attempt", 1)),
                "runtime_generation": generation,
            }
            respond(request_id, {"accepted": True})
            if mode == "crash_first" and marker and not os.path.exists(marker):
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("crashed")
                os._exit(3)
            if mode == "stale_generation":
                run["runtime_generation"] = generation + 1
            emit("message.delta", {"text": "hello"}, run, 1)
            emit("tool.requested", {"invocation_ids": ["call-1"]}, run, 2)
            emit("tool.completed", {"invocation_id": "call-1", "status": "succeeded"}, run, 3)
            if mode == "slow":
                time.sleep(5)
            emit(
                "message.completed",
                {"turn": "final", "text": "hello world", "citation_count": 1},
                run,
                4,
            )
            emit(
                "run.settled",
                {
                    "stop_reason": "completed",
                    "message": {"text": "hello world", "citations": [{"evidence_id": "e1"}]},
                    "usage": {"input_tokens": 1, "output_tokens": 2},
                },
                run,
                5,
            )
        elif method == "runtime.shutdown":
            respond(request_id, {"stopping": True})
            return 0
        else:
            respond(request_id, {"pong": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
