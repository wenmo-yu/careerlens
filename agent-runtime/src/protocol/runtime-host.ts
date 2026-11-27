import { createInterface } from "node:readline";
import type { Readable, Writable } from "node:stream";
import {
  decodeFrame,
  encodeFrame,
  type RequestFrame,
  type ResponseFrame,
  type RuntimeFrame,
} from "./jsonl.ts";
import {
  SeenRequestIds,
  lookupMethod,
  missingParams,
  runtimeError,
  type RuntimeErrorBody,
} from "./methods.ts";

export interface RuntimeHandlers {
  bind(params: Record<string, unknown>): Promise<unknown> | unknown;
  start(
    params: Record<string, unknown>,
    signal: AbortSignal,
    host: RuntimeHost,
  ): Promise<unknown> | unknown;
  cancel(params: Record<string, unknown>): Promise<unknown> | unknown;
  invoke?(params: Record<string, unknown>): Promise<unknown> | unknown;
}

interface PendingRequest {
  resolve: (frame: ResponseFrame) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/**
 * CLI-side stdio adapter.
 *
 * The reader loop never awaits a handler, so a long model stream cannot block
 * cancellation or gateway responses. Scheduler requests use `s-` IDs and CLI
 * requests use `c-` IDs; the spaces are validated in both directions.
 */
export class RuntimeHost {
  private input: Readable;
  private output: Writable;
  private handlers: RuntimeHandlers;
  private pending = new Set<Promise<unknown>>();
  private waiters = new Map<string, PendingRequest>();
  private schedulerSeq = 0;
  private cliSeq = 0;
  private controller: AbortController | undefined;
  private session: Record<string, unknown> | undefined;
  private seen = new SeenRequestIds();
  private pingSeq = 0;

  constructor(input: Readable, output: Writable, handlers: RuntimeHandlers) {
    this.input = input;
    this.output = output;
    this.handlers = handlers;
  }

  get abortSignal(): AbortSignal | undefined {
    return this.controller?.signal;
  }

  get boundSession(): Record<string, unknown> | undefined {
    return this.session;
  }

  async run(): Promise<void> {
    const lines = createInterface({ input: this.input });
    try {
      for await (const line of lines) {
        let frame: RuntimeFrame;
        try {
          frame = decodeFrame(line);
        } catch {
          this.log("discarded malformed frame");
          continue;
        }
        if (frame.type === "request") {
          this.dispatch(frame);
        } else if (frame.type === "response") {
          this.resolve(frame);
        }
      }
    } finally {
      await Promise.allSettled(this.pending);
      for (const waiter of this.waiters.values()) {
        clearTimeout(waiter.timer);
        waiter.reject(new Error("runtime host closed before response"));
      }
      this.waiters.clear();
    }
  }

  /** CLI -> Scheduler request, e.g. gateway.invoke during a model stream. */
  request(method: string, params: Record<string, unknown>): Promise<ResponseFrame> {
    const id = `c-${++this.cliSeq}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiters.delete(id);
        reject(new Error(`timeout waiting for ${method}`));
      }, 10_000);
      this.waiters.set(id, { resolve, reject, timer });
      this.write({ v: 1, type: "request", id, method, params });
    });
  }

  /** Scheduler -> CLI event projection. local_seq is host-local and not a DB seq. */
  emit(
    kind: string,
    payload: Record<string, unknown>,
    runId: string,
    attempt = 1,
    runtimeGeneration = 1,
  ): void {
    this.write({
      v: 1,
      type: "event",
      run_id: runId,
      attempt,
      runtime_generation: runtimeGeneration,
      local_seq: ++this.schedulerSeq,
      kind,
      payload,
    });
  }

  private dispatch(frame: RequestFrame): void {
    if (!/^s-[0-9]+$/.test(frame.id)) {
      this.writeError(
        frame.id,
        runtimeError("invalid_id_space", "scheduler request must use an s-<n> id"),
      );
      return;
    }
    if (this.seen.has(frame.id)) {
      this.writeError(
        frame.id,
        runtimeError("duplicate_request", `request id already used: ${frame.id}`, {
          request_id: frame.id,
        }),
      );
      return;
    }
    const spec = lookupMethod(frame.method);
    if (!spec) {
      this.writeError(frame.id, runtimeError("unknown_method", `unknown method: ${frame.method}`));
      return;
    }
    const missing = missingParams(spec, frame.params);
    if (missing.length > 0) {
      this.writeError(
        frame.id,
        runtimeError("invalid_params", `missing required params for ${frame.method}`, { missing }),
      );
      return;
    }
    if (frame.method === "run.start" && this.activeRun()) {
      this.writeError(
        frame.id,
        runtimeError("run_busy", "a run is already active in this runtime", { active: true }),
      );
      return;
    }
    this.seen.add(frame.id);
    const task = (async () => {
      try {
        let result: unknown;
        if (frame.method === "runtime.bind") {
          this.session = { ...frame.params };
          result = await this.handlers.bind(frame.params);
        } else if (frame.method === "runtime.ping") {
          this.pingSeq += 1;
          result = { pong: true, ping_seq: this.pingSeq, bound: Boolean(this.session) };
        } else if (frame.method === "run.start") {
          const controller = new AbortController();
          this.controller = controller;
          try {
            result = await this.handlers.start(frame.params, controller.signal, this);
          } finally {
            if (this.controller === controller) this.controller = undefined;
          }
        } else if (frame.method === "run.cancel") {
          const hadActiveRun = Boolean(this.activeRun());
          this.controller?.abort();
          result = { ...(await this.handlers.cancel(frame.params)), hadActiveRun };
        } else if (frame.method === "gateway.invoke") {
          result = this.handlers.invoke
            ? await this.handlers.invoke(frame.params)
            : { error: "gateway_not_available" };
        } else {
          throw new Error(`unreachable method: ${frame.method}`);
        }
        this.writeResponse(frame.id, true, result);
      } catch (error) {
        this.writeError(
          frame.id,
          runtimeError("handler_error", error instanceof Error ? error.message : String(error)),
        );
      }
    })();
    this.pending.add(task);
    void task.finally(() => this.pending.delete(task));
  }

  private activeRun(): AbortController | undefined {
    return this.controller && !this.controller.signal.aborted ? this.controller : undefined;
  }

  private resolve(frame: ResponseFrame): void {
    if (!/^c-[0-9]+$/.test(frame.id)) {
      this.log("discarded response with invalid id space");
      return;
    }
    const waiter = this.waiters.get(frame.id);
    if (!waiter) {
      this.log("discarded response with no matching request");
      return;
    }
    this.waiters.delete(frame.id);
    clearTimeout(waiter.timer);
    waiter.resolve(frame);
  }

  private writeResponse(id: string, ok: boolean, result?: unknown): void {
    const frame: ResponseFrame = { v: 1, type: "response", id, ok, result };
    this.write(frame);
  }

  private writeError(id: string, error: RuntimeErrorBody): void {
    const frame: ResponseFrame = { v: 1, type: "response", id, ok: false, error };
    this.write(frame);
  }

  private write(frame: RuntimeFrame): void {
    this.output.write(`${encodeFrame(frame)}\n`);
  }

  private log(message: string): void {
    process.stderr.write(`[runtime-host] ${message}\n`);
  }
}
