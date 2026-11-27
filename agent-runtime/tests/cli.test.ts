import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  decodeFrame,
  encodeFrame,
  type EventFrame,
  type RequestFrame,
  type ResponseFrame,
  type RuntimeFrame,
} from "../src/protocol/jsonl.ts";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");

function waitFor(predicate: () => boolean, timeoutMs = 10_000): Promise<void> {
  return new Promise((resolvePromise, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) {
        clearInterval(timer);
        resolvePromise();
      } else if (Date.now() - started > timeoutMs) {
        clearInterval(timer);
        reject(new Error("CLI condition timed out"));
      }
    }, 10);
  });
}

test("CLI integration: bind, tool round trip, settled event, protocol-only stdout", async () => {
  const child = spawn(process.execPath, [resolve(packageRoot, "src/cli.ts")], {
    cwd: packageRoot,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const frames: RuntimeFrame[] = [];
  const rawLines: string[] = [];
  let buffer = "";
  child.stdout.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    let index = buffer.indexOf("\n");
    while (index >= 0) {
      const line = buffer.slice(0, index);
      buffer = buffer.slice(index + 1);
      rawLines.push(line);
      frames.push(decodeFrame(line));
      index = buffer.indexOf("\n");
    }
  });

  const send = (frame: RuntimeFrame): void => {
    child.stdin.write(`${encodeFrame(frame)}\n`);
  };

  send({ v: 1, type: "request", id: "s-1", method: "runtime.bind", params: { session_id: "s1" } });
  send({
    v: 1,
    type: "request",
    id: "s-2",
    method: "run.start",
    params: { run_id: "r1", attempt: 1, runtime_generation: 1 },
  });

  await waitFor(() => frames.some((frame) => frame.type === "request"));
  const gateway = frames.find((frame) => frame.type === "request") as RequestFrame;
  assert.equal(gateway.method, "gateway.invoke");
  assert.match(gateway.id, /^c-[0-9]+$/);
  send({
    v: 1,
    type: "response",
    id: gateway.id,
    ok: true,
    result: { evidenceIds: ["E01"] },
  });

  await waitFor(() =>
    frames.some(
      (frame) =>
        frame.type === "event" &&
        frame.kind === "run.settled" &&
        (frame as EventFrame).payload.stopReason === "completed",
    ),
  );
  await waitFor(() => frames.some((frame) => frame.type === "response" && frame.id === "s-2"));

  assert.ok(rawLines.length > 0);
  assert.equal(rawLines.length, frames.length, "every stdout line must be a protocol frame");
  const bindResponse = frames.find((frame) => frame.type === "response" && frame.id === "s-1") as ResponseFrame;
  assert.equal(bindResponse.ok, true);
  const startResponse = frames.find((frame) => frame.type === "response" && frame.id === "s-2") as ResponseFrame;
  assert.equal(startResponse.ok, true);
  const kinds = frames.filter((frame) => frame.type === "event").map((frame) => (frame as EventFrame).kind);
  assert.ok(kinds.includes("tool.requested"));
  assert.ok(kinds.includes("tool.completed"));
  assert.ok(kinds.includes("run.settled"));

  child.stdin.end();
  const exitCode = await new Promise<number | null>((resolveExit) => child.on("exit", resolveExit));
  assert.equal(exitCode, 0);
});
