import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { PassThrough } from "node:stream";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { decodeFrame, encodeFrame, type ResponseFrame, type RuntimeFrame } from "../src/protocol/jsonl.ts";
import { METHODS, RETRYABLE, lookupMethod } from "../src/protocol/methods.ts";
import { RuntimeHost, type RuntimeHandlers } from "../src/protocol/runtime-host.ts";

function waitFor(predicate: () => boolean, timeoutMs = 5_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - started > timeoutMs) {
        clearInterval(timer);
        reject(new Error("condition timed out"));
      }
    }, 5);
  });
}

function collectFrames(output: PassThrough): RuntimeFrame[] {
  const frames: RuntimeFrame[] = [];
  let buffer = "";
  output.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    let index = buffer.indexOf("\n");
    while (index >= 0) {
      const line = buffer.slice(0, index);
      buffer = buffer.slice(index + 1);
      frames.push(decodeFrame(line));
      index = buffer.indexOf("\n");
    }
  });
  return frames;
}

function send(input: PassThrough, frame: RuntimeFrame): void {
  input.write(`${encodeFrame(frame)}\n`);
}

function response(frames: RuntimeFrame[], id: string): ResponseFrame | undefined {
  return frames.find(
    (frame) => frame.type === "response" && (frame as ResponseFrame).id === id,
  ) as ResponseFrame | undefined;
}

function build(handlers: Partial<RuntimeHandlers> = {}) {
  const input = new PassThrough();
  const output = new PassThrough();
  const frames = collectFrames(output);
  const host = new RuntimeHost(input, output, {
    bind: (params) => ({ sessionId: params.session_id }),
    start: () => ({ started: true }),
    cancel: () => ({ cancelled: true }),
    ...handlers,
  });
  return { input, output, frames, host, running: host.run() };
}

test("M3: unknown method is rejected as unknown_method without invoking handlers", async () => {
  let startCalls = 0;
  const { input, frames, running } = build({
    start: () => {
      startCalls += 1;
      return { started: true };
    },
  });
  send(input, { v: 1, type: "request", id: "s-1", method: "run.start", params: { run_id: "r1" } });
  send(input, { v: 1, type: "request", id: "s-2", method: "run.pause", params: {} });
  await waitFor(() => frames.length >= 2);
  const unknown = response(frames, "s-2");
  assert.equal(unknown?.ok, false);
  assert.equal(unknown?.error?.code, "unknown_method");
  assert.equal(unknown?.error?.retryable, false);
  assert.equal(startCalls, 1);
  input.end();
  await running;
});

test("M3: missing required params produce invalid_params with details.missing", async () => {
  const { input, frames, running } = build();
  send(input, { v: 1, type: "request", id: "s-1", method: "run.start", params: {} });
  send(input, { v: 1, type: "request", id: "s-2", method: "runtime.bind", params: { session_id: "" } });
  await waitFor(() => frames.length >= 2);
  const start = response(frames, "s-1");
  assert.equal(start?.ok, false);
  assert.equal(start?.error?.code, "invalid_params");
  assert.deepEqual(start?.error?.details?.missing, ["run_id"]);
  const bind = response(frames, "s-2");
  assert.equal(bind?.error?.code, "invalid_params");
  assert.deepEqual(bind?.error?.details?.missing, ["session_id"]);
  input.end();
  await running;
});

test("M3: duplicate request id is rejected and does not double-execute", async () => {
  let calls = 0;
  const { input, frames, running } = build({
    cancel: () => {
      calls += 1;
      return { cancelled: true };
    },
  });
  send(input, { v: 1, type: "request", id: "s-1", method: "run.cancel", params: {} });
  await waitFor(() => frames.length >= 1);
  send(input, { v: 1, type: "request", id: "s-1", method: "run.cancel", params: {} });
  await waitFor(() => frames.length >= 2);
  const replies = frames.filter(
    (frame) => frame.type === "response" && (frame as ResponseFrame).id === "s-1",
  ) as ResponseFrame[];
  assert.equal(replies.length, 2);
  assert.equal(replies[0]?.ok, true);
  const duplicate = replies[1];
  assert.equal(duplicate?.ok, false);
  assert.equal(duplicate?.error?.code, "duplicate_request");
  assert.equal(calls, 1);
  input.end();
  await running;
});

test("M3: runtime.ping reports bind state and increments ping_seq", async () => {
  const { input, frames, running } = build();
  send(input, { v: 1, type: "request", id: "s-1", method: "runtime.ping", params: {} });
  await waitFor(() => frames.length >= 1);
  const before = response(frames, "s-1");
  assert.deepEqual(before?.result, { pong: true, ping_seq: 1, bound: false });

  send(input, { v: 1, type: "request", id: "s-2", method: "runtime.bind", params: { session_id: "s1" } });
  send(input, { v: 1, type: "request", id: "s-3", method: "runtime.ping", params: {} });
  await waitFor(() => frames.length >= 3);
  const after = response(frames, "s-3");
  assert.deepEqual(after?.result, { pong: true, ping_seq: 2, bound: true });
  input.end();
  await running;
});

test("M3: run.start is rejected with retryable run_busy while a run is active", async () => {
  let release: (() => void) | undefined;
  let startCalls = 0;
  const { input, frames, running } = build({
    start: async (_params, signal) => {
      startCalls += 1;
      if (startCalls > 1) return { started: true, resumed: true };
      await new Promise<void>((resolve) => {
        release = resolve;
        signal.addEventListener("abort", () => resolve(), { once: true });
      });
      return { started: true, aborted: signal.aborted };
    },
    cancel: () => {
      release?.();
      return { cancelled: true };
    },
  });

  send(input, { v: 1, type: "request", id: "s-1", method: "run.start", params: { run_id: "r1" } });
  await waitFor(() => startCalls === 1);
  send(input, { v: 1, type: "request", id: "s-2", method: "run.start", params: { run_id: "r2" } });
  await waitFor(() => response(frames, "s-2") !== undefined);
  const busy = response(frames, "s-2");
  assert.equal(busy?.error?.code, "run_busy");
  assert.equal(busy?.error?.retryable, true);

  send(input, { v: 1, type: "request", id: "s-3", method: "run.cancel", params: { run_id: "r1" } });
  await waitFor(() => response(frames, "s-1") !== undefined && response(frames, "s-3") !== undefined);

  send(input, { v: 1, type: "request", id: "s-4", method: "run.start", params: { run_id: "r3" } });
  await waitFor(() => response(frames, "s-4") !== undefined);
  assert.equal(response(frames, "s-4")?.ok, true);
  assert.equal(startCalls, 2);
  input.end();
  await running;
});

test("M3: contract JSON and runtime registry stay in sync", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const contractPath = resolve(here, "../../contracts/runtime-jsonl-v1.methods.json");
  const contract = JSON.parse(readFileSync(contractPath, "utf8")) as {
    methods: { name: string; required_params: string[] }[];
    error_codes: { code: string; retryable: boolean }[];
  };

  const contractNames = contract.methods.map((entry) => entry.name).sort();
  assert.deepEqual(contractNames, [...METHODS.keys()].sort());

  for (const entry of contract.methods) {
    const spec = lookupMethod(entry.name);
    assert.ok(spec, `missing spec for ${entry.name}`);
    assert.deepEqual(spec.requiredParams, entry.required_params);
  }

  for (const entry of contract.error_codes) {
    assert.equal(RETRYABLE[entry.code as keyof typeof RETRYABLE], entry.retryable, entry.code);
  }
});
