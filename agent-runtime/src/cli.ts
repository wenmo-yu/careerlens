import {
  InMemoryApprovals,
  InMemoryStore,
  ScriptedModel,
} from "./engine/in-memory-ports.ts";
import { InMemoryBudget } from "./engine/budget.ts";
import { runEngine } from "./engine/runner.ts";
import { ToolGateway } from "./engine/tool-executor.ts";
import type { EventSink, ModelDelta, RunInput, ToolDefinition } from "./engine/types.ts";
import { RuntimeHost } from "./protocol/runtime-host.ts";

const TOOLS: ToolDefinition[] = [
  {
    name: "search_evidence",
    version: "1",
    sideEffectClass: "read_only",
    approvalPolicy: "allow",
    description: "Synthetic read-only evidence lookup for the M0 prototype",
  },
];

const SCRIPT: ModelDelta[][] = [
  [
    { kind: "text_delta", text: "我先检索一条合成证据。" },
    {
      kind: "tool_call_delta",
      index: 0,
      name: "search_evidence",
      providerCallId: "pcall-1",
      argsChunk: '{"query":',
    },
    { kind: "tool_call_delta", index: 0, argsChunk: '"Docker"}', providerCallId: "pcall-1" },
    { kind: "usage", inputTokens: 20, outputTokens: 8 },
    { kind: "finish", reason: "tool_calls" },
  ],
  [
    { kind: "text_delta", text: "已根据合成证据完成回答。" },
    { kind: "usage", inputTokens: 30, outputTokens: 12 },
    { kind: "finish", reason: "stop" },
  ],
];

function stringParam(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

const host = new RuntimeHost(process.stdin, process.stdout, {
  bind(params) {
    return { session_id: stringParam(params.session_id, "missing"), bound: true };
  },
  async start(params, signal, runtime) {
    const runId = stringParam(params.run_id, "run-m0");
    const sessionId = stringParam(runtime.boundSession?.session_id, "session-m0");
    const attempt = typeof params.attempt === "number" ? params.attempt : 1;
    const generation =
      typeof params.runtime_generation === "number" ? params.runtime_generation : 1;
    const input: RunInput = {
      runId,
      sessionId,
      goal: stringParam(params.goal, "M0 scripted run"),
      inputRevisionRef: "input-m0",
    };

    const events: EventSink = {
      emit(event) {
        runtime.emit(event.kind, event.payload, runId, attempt, generation);
      },
    };
    const tools = new ToolGateway(TOOLS, {
      search_evidence: async (args) => {
        // Tool capability stays with the scheduler/broker side: the CLI asks
        // for execution over the same bidirectional JSONL channel.
        const response = await runtime.request("gateway.invoke", {
          run_id: runId,
          tool: "search_evidence",
          args,
        });
        if (!response.ok) return { error: "gateway_error" };
        return response.result;
      },
    });

    const outcome = await runEngine(
      {
        id: "careerlens-m0",
        version: "0.1.0-m0",
        instructions: "M0 prototype only; no real model and no real evidence.",
        toolIds: ["search_evidence"],
        modelConfigRef: "scripted-model",
        outputSchemaRef: "m0-text",
      },
      input,
      {
        model: new ScriptedModel(SCRIPT.map((deltas) => ({ deltas, delayMs: 15 }))),
        tools,
        store: new InMemoryStore(),
        budget: new InMemoryBudget({ maxTurns: 4, maxToolCalls: 8 }),
        events,
        approvals: new InMemoryApprovals(),
      },
      signal,
    );
    return { accepted: true, outcome };
  },
  cancel() {
    return { cancel_requested: true };
  },
});

void host.run().catch((error: unknown) => {
  process.stderr.write(`[runtime] ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
