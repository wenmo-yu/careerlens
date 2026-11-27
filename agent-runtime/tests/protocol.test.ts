import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import test from "node:test";
import {
  decodeFrame,
  FrameDecoder,
  FrameError,
  MAX_FRAME_BYTES,
  encodeFrame,
  type RequestFrame,
  type ResponseFrame,
  type RuntimeFrame,
} from "../src/protocol/jsonl.ts";
import { RuntimeHost } from "../src/protocol/runtime-host.ts";

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

test("v1 frame codec rejects CRLF, invalid JSON and oversized frames", () => {
  assert.throws(() => decodeFrame('{"v":1,"type":"event"}\r'), FrameError);
  assert.throws(() => decodeFrame("not json"), FrameError);
  assert.throws(() => decodeFrame(`{"v":1,"type":"request","id":"s-1","method":"m","params":{},"pad":"${"x".repeat(MAX_FRAME_BYTES)}"}`), FrameError);
  const frame: RequestFrame = {
    v: 1,
    type: "request",
    id: "s-1",
    method: "runtime.bind",
    params: { session_id: "s1" },
  };
  assert.deepEqual(decodeFrame(encodeFrame(frame)), frame);
});

test("streaming decoder buffers half lines and rejects invalid UTF-8", () => {
  const decoder = new FrameDecoder();
  const first = '{"v":1,"type":"request","id":"s-1","method":"runtime.bind","params":{';
  const second = '"session_id":"s1"}}\n';
  assert.deepEqual(decoder.push(Buffer.from(first)), []);
  const lines = decoder.push(Buffer.from(second));
  assert.equal(lines.length, 1);
  assert.equal((decodeFrame(lines[0] as string) as RequestFrame).method, "runtime.bind");
  assert.throws(() => decoder.push(Buffer.from([0xff, 0xfe])), /fatal|encoded|UTF-8|invalid/i);
});

test("T32: reader handles cancel while start handler is still awaiting", async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  const frames = collectFrames(output);
  let release: (() => void) | undefined;
  let observedAbort = false;
  const host = new RuntimeHost(input, output, {
    bind: (params) => ({ bound: params.session_id }),
    async start(_params, signal) {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      observedAbort = signal.aborted;
      return { started: true };
    },
    cancel: () => {
      release?.();
      return { cancelled: true };
    },
  });
  const running = host.run();
  send(input, { v: 1, type: "request", id: "s-1", method: "runtime.bind", params: { session_id: "s1" } });
  send(input, { v: 1, type: "request", id: "s-2", method: "run.start", params: { run_id: "r1" } });
  send(input, { v: 1, type: "request", id: "s-3", method: "run.cancel", params: { run_id: "r1" } });
  await waitFor(() => frames.length >= 3);
  const ids = frames.map((frame) => (frame as ResponseFrame).id);
  assert.deepEqual(ids, ["s-1", "s-3", "s-2"]);
  assert.equal(observedAbort, true);
  input.end();
  await running;
});

test("T32: CLI-originated gateway.invoke is paired by c- namespace", async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  const frames = collectFrames(output);
  const host = new RuntimeHost(input, output, {
    bind: () => ({ bound: true }),
    async start(_params, _signal, runtime) {
      const response = await runtime.request("gateway.invoke", { tool: "search_evidence" });
      return { result: response.result };
    },
    cancel: () => ({ cancelled: true }),
  });
  const running = host.run();
  send(input, { v: 1, type: "request", id: "s-1", method: "run.start", params: { run_id: "r1" } });
  await waitFor(() => frames.some((frame) => frame.type === "request"));
  const request = frames.find((frame) => frame.type === "request") as RequestFrame;
  assert.match(request.id, /^c-[0-9]+$/);
  assert.equal(request.method, "gateway.invoke");
  send(input, { v: 1, type: "response", id: request.id, ok: true, result: { evidenceIds: ["E01"] } });
  await waitFor(() => frames.some((frame) => frame.type === "response" && frame.id === "s-1"));
  const startResponse = frames.find(
    (frame) => frame.type === "response" && frame.id === "s-1",
  ) as ResponseFrame;
  assert.deepEqual(startResponse.result, { result: { evidenceIds: ["E01"] } });
  input.end();
  await running;
});

test("scheduler request ids from the CLI namespace are rejected", async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  const frames = collectFrames(output);
  const host = new RuntimeHost(input, output, {
    bind: () => ({ bound: true }),
    start: () => ({ started: true }),
    cancel: () => ({ cancelled: true }),
  });
  const running = host.run();
  send(input, { v: 1, type: "request", id: "c-99", method: "runtime.bind", params: {} });
  await waitFor(() => frames.length >= 1);
  const response = frames[0] as ResponseFrame;
  assert.equal(response.ok, false);
  assert.equal(response.error?.code, "invalid_id_space");
  input.end();
  await running;
});
