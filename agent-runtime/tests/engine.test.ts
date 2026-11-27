import assert from "node:assert/strict";
import test from "node:test";
import { InMemoryApprovals, InMemoryStore, ScriptedModel } from "../src/engine/in-memory-ports.ts";
import { InMemoryBudget } from "../src/engine/budget.ts";
import { deserializeCheckpoint, serializeCheckpoint } from "../src/engine/restore.ts";
import { runEngine, resumeEngine } from "../src/engine/runner.ts";
import { ToolGateway } from "../src/engine/tool-executor.ts";
import type {
  ApprovalClient,
  BudgetClient,
  DurableBoundaryClient,
  EnginePorts,
  EngineSpec,
  EventSink,
  ModelPort,
  RunInput,
  ToolDefinition,
  ToolExecutor,
} from "../src/engine/types.ts";

const input: RunInput = {
  runId: "run-1",
  sessionId: "session-1",
  goal: "M0 fixture",
  inputRevisionRef: "input-1",
};

function portsFor(
  model: ModelPort,
  tools: ToolExecutor,
  options: { budget?: BudgetClient; approvals?: ApprovalClient } = {},
): {
  ports: EnginePorts;
  store: DurableBoundaryClient;
  events: EventSink & { events: { kind: string; payload: Record<string, unknown> }[] };
} {
  const store = new InMemoryStore();
  const events = new (class implements EventSink {
    events: { kind: string; payload: Record<string, unknown> }[] = [];
    emit(event: { kind: string; payload: Record<string, unknown> }): void {
      this.events.push(event);
    }
  })();
  return {
    ports: {
      model,
      tools,
      store,
      budget: options.budget ?? new InMemoryBudget({ maxTurns: 6, maxToolCalls: 12 }),
      approvals: options.approvals ?? new InMemoryApprovals(),
      events,
    },
    store,
    events,
  };
}

function specFor(tools: ToolDefinition[]): EngineSpec {
  return {
    id: "careerlens-m0",
    version: "0.1.0-m0",
    instructions: "fixture",
    toolIds: tools.map((tool) => tool.name),
    modelConfigRef: "scripted",
    outputSchemaRef: "m0-text",
  };
}

const readOnly: ToolDefinition = {
  name: "search_evidence",
  version: "1",
  sideEffectClass: "read_only",
  approvalPolicy: "allow",
  description: "fixture",
};

test("zero-tool run settles completed without any tool intent", async () => {
  const model = new ScriptedModel([
    {
      deltas: [
        { kind: "text_delta", text: "hello" },
        { kind: "usage", inputTokens: 4, outputTokens: 2 },
        { kind: "finish", reason: "stop" },
      ],
    },
  ]);
  const calls: string[] = [];
  const tools = new ToolGateway([readOnly], {
    search_evidence: () => calls.push("called"),
  });
  const { ports } = portsFor(model, tools);
  const outcome = await runEngine(specFor([readOnly]), input, ports, new AbortController().signal);
  assert.equal(outcome.stopReason, "completed");
  assert.equal(outcome.finalText, "hello");
  assert.equal(outcome.usage.inputTokens, 4);
  assert.deepEqual(calls, []);
});

test("T28: truncated / invalid argument JSON never executes a tool", async () => {
  for (const badChunk of ['{"query":', '{"query": nope}', '{"query": "x"'] ) {
    const model = new ScriptedModel([
      {
        deltas: [
          { kind: "text_delta", text: "partial" },
          {
            kind: "tool_call_delta",
            index: 0,
            name: "search_evidence",
            providerCallId: "pcall",
            argsChunk: badChunk,
          },
          { kind: "finish", reason: "tool_calls" },
        ],
      },
    ]);
    let invoked = 0;
    const tools = new ToolGateway([readOnly], {
      search_evidence: () => {
        invoked += 1;
        return "unexpected";
      },
    });
    const { ports, store } = portsFor(model, tools);
    const outcome = await runEngine(specFor([readOnly]), input, ports, new AbortController().signal);
    assert.equal(outcome.stopReason, "model_error");
    assert.equal(invoked, 0);
    assert.equal(store.messages().length, 0);
  }
});

test("T28: replayed identical delta produces one intent; full tool round trip", async () => {
  const model = new ScriptedModel([
    {
      deltas: [
        { kind: "tool_call_delta", index: 0, name: "search_evidence", providerCallId: "pcall", argsChunk: '{"q":' },
        { kind: "tool_call_delta", index: 0, name: "search_evidence", providerCallId: "pcall", argsChunk: '{"q":' },
        { kind: "tool_call_delta", index: 0, argsChunk: '"Docker"}', providerCallId: "pcall" },
        { kind: "finish", reason: "tool_calls" },
      ],
    },
    {
      deltas: [
        { kind: "text_delta", text: "done" },
        { kind: "finish", reason: "stop" },
      ],
    },
  ]);
  let invoked = 0;
  const tools = new ToolGateway([readOnly], {
    search_evidence: (args) => {
      invoked += 1;
      assert.deepEqual(args, { q: "Docker" });
      return { evidenceIds: ["E01"] };
    },
  });
  const { ports, store } = portsFor(model, tools);
  const outcome = await runEngine(specFor([readOnly]), input, ports, new AbortController().signal);
  assert.equal(outcome.stopReason, "completed");
  assert.equal(outcome.finalText, "done");
  assert.equal(invoked, 1);
  assert.equal(store.messages()[0]?.toolIntents.length, 1);
  assert.equal(model.requests.length, 2);
});

test("T29: approval barrier stops later tools and resume executes only the remainder", async () => {
  const definitions: ToolDefinition[] = [
    { name: "read_one", version: "1", sideEffectClass: "read_only", approvalPolicy: "allow", description: "" },
    { name: "write_two", version: "1", sideEffectClass: "write", approvalPolicy: "ask", description: "" },
    { name: "read_three", version: "1", sideEffectClass: "read_only", approvalPolicy: "allow", description: "" },
  ];
  const model = new ScriptedModel([
    {
      deltas: [
        ...definitions.map((definition, index) => ({
          kind: "tool_call_delta" as const,
          index,
          name: definition.name,
          providerCallId: `pcall-${index}`,
          argsChunk: "{}",
        })),
        { kind: "finish", reason: "tool_calls" },
      ],
    },
    {
      deltas: [
        { kind: "text_delta", text: "approved and finished" },
        { kind: "finish", reason: "stop" },
      ],
    },
  ]);
  const executed: string[] = [];
  const tools = new ToolGateway(definitions, {
    read_one: () => {
      executed.push("read_one");
      return "1";
    },
    write_two: () => {
      executed.push("write_two");
      return "2";
    },
    read_three: () => {
      executed.push("read_three");
      return "3";
    },
  });
  const approvals = new InMemoryApprovals();
  const { ports, store } = portsFor(model, tools, { approvals });
  const first = await runEngine(specFor(definitions), input, ports, new AbortController().signal);
  assert.equal(first.stopReason, "approval_required");
  assert.deepEqual(executed, ["read_one"]);
  assert.equal(store.pendingIntents().length, 2);

  const approvalId = approvals.approvalFor("run-1:turn-1:1");
  assert.ok(approvalId);
  approvals.decide(approvalId, "approved");
  const checkpoint = deserializeCheckpoint(serializeCheckpoint(first.checkpoint as never));
  const second = await resumeEngine(specFor(definitions), checkpoint, ports, new AbortController().signal);
  assert.equal(second.stopReason, "completed");
  assert.equal(second.finalText, "approved and finished");
  assert.deepEqual(executed, ["read_one", "write_two", "read_three"]);
  assert.equal(model.requests.length, 2, "resume must not re-request the committed model turn");
  assert.equal(approvals.consume(approvalId), false, "approval is consumed exactly once");
});

test("T29: denied approval yields a structured tool result and still completes", async () => {
  const definitions: ToolDefinition[] = [
    { name: "send_external", version: "1", sideEffectClass: "external", approvalPolicy: "ask", description: "" },
  ];
  const model = new ScriptedModel([
    {
      deltas: [
        { kind: "tool_call_delta", index: 0, name: "send_external", providerCallId: "pcall", argsChunk: "{}" },
        { kind: "finish", reason: "tool_calls" },
      ],
    },
    { deltas: [{ kind: "text_delta", text: "not sent" }, { kind: "finish", reason: "stop" }] },
  ]);
  const approvals = new InMemoryApprovals();
  const { ports, store } = portsFor(
    model,
    new ToolGateway(definitions, {
      send_external: () => {
        throw new Error("must not execute after denial");
      },
    }),
    { approvals },
  );
  const first = await runEngine(specFor(definitions), input, ports, new AbortController().signal);
  const approvalId = approvals.approvalFor("run-1:turn-1:0");
  assert.ok(approvalId);
  approvals.decide(approvalId, "denied");
  const second = await resumeEngine(specFor(definitions), first.checkpoint, ports, new AbortController().signal);
  assert.equal(second.stopReason, "completed");
  assert.equal(store.getResult("run-1:turn-1:0")?.status, "denied");
});

test("T28/T32: cancellation during a slow model stream stops before tool execution", async () => {
  const deltas = Array.from({ length: 12 }, () => ({ kind: "text_delta" as const, text: "x" }));
  deltas.push({ kind: "finish", reason: "stop" });
  const model = new ScriptedModel([{ deltas, delayMs: 15 }]);
  let invoked = 0;
  const tools = new ToolGateway([readOnly], {
    search_evidence: () => {
      invoked += 1;
    },
  });
  const { ports, store } = portsFor(model, tools);
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 25);
  const outcome = await runEngine(specFor([readOnly]), input, ports, controller.signal);
  assert.equal(outcome.stopReason, "cancelled");
  assert.equal(invoked, 0);
  assert.equal(store.messages().length, 0);
});

test("T36: budget survives a second turn and stops with budget_exhausted", async () => {
  const model = new ScriptedModel([
    {
      deltas: [
        { kind: "tool_call_delta", index: 0, name: "search_evidence", providerCallId: "pcall", argsChunk: "{}" },
        { kind: "finish", reason: "tool_calls" },
      ],
    },
    { deltas: [{ kind: "text_delta", text: "never" }, { kind: "finish", reason: "stop" }] },
  ]);
  const tools = new ToolGateway([readOnly], { search_evidence: () => "ok" });
  const { ports } = portsFor(model, tools, {
    budget: new InMemoryBudget({ maxTurns: 1, maxToolCalls: 4 }),
  });
  const outcome = await runEngine(specFor([readOnly]), input, ports, new AbortController().signal);
  assert.equal(outcome.stopReason, "budget_exhausted");
  assert.equal(outcome.usage.modelTurns, 1);
  assert.equal(outcome.usage.toolCalls, 1);
});

test("restore rejects foreign checkpoint versions", () => {
  assert.throws(
    () => deserializeCheckpoint('{"schemaVersion":99,"engineVersion":"0.1.0-m0"}'),
    /unsupported checkpoint/,
  );
});
