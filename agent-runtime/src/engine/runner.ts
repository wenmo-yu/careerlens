import { collectModelStream, ModelStreamError } from "./model-stream.ts";
import { digestArgs } from "./in-memory-ports.ts";
import { CHECKPOINT_SCHEMA_VERSION, M0_ENGINE_VERSION, validateCheckpoint } from "./restore.ts";
import type {
  EngineOutcome,
  EnginePorts,
  EngineSpec,
  RunInput,
  SafeCheckpoint,
  ToolResultRecord,
  Usage,
} from "./types.ts";

/**
 * M0 prototype of the CareerLens model/tool loop.
 *
 * Invariants kept here:
 * - the model response is complete and valid before any tool intent exists;
 * - an invocation ID is stable across attempts;
 * - an approval barrier stops later tools in the same turn;
 * - a committed tool result is never re-executed on resume;
 * - only a successful validate step yields `completed`; approval_required is
 *   an exit from this attempt, not a terminal Run state.
 */
export async function runEngine(
  spec: EngineSpec,
  input: RunInput,
  ports: EnginePorts,
  signal: AbortSignal,
): Promise<EngineOutcome> {
  ports.store.saveInput(input);
  ports.store.saveCheckpoint({
    schemaVersion: CHECKPOINT_SCHEMA_VERSION,
    engineVersion: M0_ENGINE_VERSION,
    runId: input.runId,
    sessionId: input.sessionId,
    turnId: "turn-0",
    next: "model",
    messageHeadRef: "",
    completedInvocationIds: [],
    pendingInvocationIds: [],
    budgetRef: "budget-m0",
    policyRevision: "policy-m0",
    toolSnapshotRef: "tools-m0",
    inputRevisionRef: input.inputRevisionRef,
  });
  return continueEngine(spec, ports, signal);
}

export async function resumeEngine(
  spec: EngineSpec,
  checkpoint: unknown,
  ports: EnginePorts,
  signal: AbortSignal,
): Promise<EngineOutcome> {
  const cp = validateCheckpoint(checkpoint);
  const input = ports.store.getInput(cp.runId);
  if (!input || input.sessionId !== cp.sessionId) {
    throw new Error("checkpoint input is not available in this store");
  }
  ports.store.saveCheckpoint(cp);
  return continueEngine(spec, ports, signal);
}

interface LoopState {
  localSeq: number;
}

async function continueEngine(
  spec: EngineSpec,
  ports: EnginePorts,
  signal: AbortSignal,
): Promise<EngineOutcome> {
  const input = ports.store.getInput(
    ports.store.getCheckpoint()?.runId ?? "",
  );
  if (!input) throw new Error("missing durable run input");

  const allowed = ports.tools
    .definitions()
    .filter((definition) => spec.toolIds.includes(definition.name));
  const versions = new Map(allowed.map((definition) => [definition.name, definition.version]));
  const state: LoopState = { localSeq: 0 };

  const emit = (kind: string, payload: Record<string, unknown>): void => {
    ports.events.emit({
      kind,
      runId: input.runId,
      localSeq: ++state.localSeq,
      payload,
    });
  };

  const checkpointFor = (
    turnId: string,
    next: SafeCheckpoint["next"],
    completed: string[],
    pending: string[],
  ): SafeCheckpoint => ({
    schemaVersion: CHECKPOINT_SCHEMA_VERSION,
    engineVersion: M0_ENGINE_VERSION,
    runId: input.runId,
    sessionId: input.sessionId,
    turnId,
    next,
    messageHeadRef: `${input.runId}:${turnId}`,
    completedInvocationIds: completed,
    pendingInvocationIds: pending,
    budgetRef: "budget-m0",
    policyRevision: "policy-m0",
    toolSnapshotRef: "tools-m0",
    inputRevisionRef: input.inputRevisionRef,
  });

  const finish = (stopReason: EngineOutcome["stopReason"], finalText: string): EngineOutcome => {
    const snapshot = ports.budget.snapshot();
    const usage: Usage = {
      modelTurns: snapshot.turns,
      toolCalls: snapshot.toolCalls,
      inputTokens: snapshot.inputTokens,
      outputTokens: snapshot.outputTokens,
    };
    emit(
      stopReason === "approval_required" ? "run.waiting_approval" : "run.settled",
      { stopReason },
    );
    return { stopReason, finalText, usage, checkpoint: ports.store.getCheckpoint() };
  };

  for (;;) {
    const checkpoint = ports.store.getCheckpoint();
    if (!checkpoint) throw new Error("missing checkpoint");
    if (signal.aborted) return finish("cancelled", "");

    if (checkpoint.next === "model") {
      if (!ports.budget.reserve("turn")) return finish("budget_exhausted", "");

      const turnId = `turn-${ports.store.messages().length + 1}`;
      let response;
      try {
        response = await collectModelStream(
          ports.model.stream(
            { turnId, spec, input, messages: ports.store.messages(), tools: allowed },
            signal,
          ),
          signal,
        );
      } catch (error) {
        // A stream that ended before tool intent commit is safe to abandon.
        // A committed intent is never re-requested: resume enters at `tools`.
        if (error instanceof ModelStreamError) {
          return finish(signal.aborted ? "cancelled" : "model_error", "");
        }
        return finish("interrupted", "");
      }
      ports.budget.consume(response.usage);

      const intents = response.toolCalls.map((call) => ({
        invocationId: `${input.runId}:${turnId}:${call.ordinal}`,
        providerCallId: call.providerCallId,
        turnId,
        ordinal: call.ordinal,
        name: call.name,
        version: versions.get(call.name) ?? "unknown",
        args: call.args,
        argsDigest: digestArgs(call.args),
      }));

      ports.store.appendMessage({
        messageId: `${input.runId}:${turnId}:assistant`,
        turnId,
        text: response.text,
        toolIntents: intents,
      });
      emit("message.completed", {
        turnId,
        text: response.text,
        invocationIds: intents.map((intent) => intent.invocationId),
      });

      if (intents.length > 0) {
        ports.store.commitIntents(intents);
        ports.store.saveCheckpoint(
          checkpointFor(turnId, "tools", [], intents.map((intent) => intent.invocationId)),
        );
        emit("tool.requested", {
          invocationIds: intents.map((intent) => intent.invocationId),
        });
      } else {
        ports.store.saveCheckpoint(checkpointFor(turnId, "validate", [], []));
      }
      continue;
    }

    if (checkpoint.next === "tools") {
      for (const intent of ports.store.pendingIntents()) {
        if (signal.aborted) return finish("cancelled", "");
        const definition = allowed.find(
          (item) => item.name === intent.name && item.version === intent.version,
        );
        const policy = definition?.approvalPolicy ?? "deny";

        if (policy === "deny") {
          ports.store.saveResult(denied(intent, "tool_denied"));
          emit("tool.completed", { invocationId: intent.invocationId, status: "denied" });
          continue;
        }

        if (policy === "ask") {
          const approvalId = ports.approvals.approvalFor(intent.invocationId) ??
            ports.approvals.request(intent, intent.argsDigest);
          const decision = ports.approvals.decision(approvalId);
          if (decision === "pending") {
            ports.store.saveCheckpoint(checkpointFor(
              checkpoint.turnId,
              "tools",
              completedIds(ports),
              ports.store.pendingIntents().map((item) => item.invocationId),
            ));
            emit("approval.requested", {
              approvalId,
              invocationId: intent.invocationId,
              argsDigest: intent.argsDigest,
            });
            return finish("approval_required", "");
          }
          if (
            decision === "denied" ||
            ports.approvals.digestOf(approvalId) !== intent.argsDigest ||
            !ports.approvals.consume(approvalId)
          ) {
            ports.store.saveResult(denied(intent, "approval_not_consumed"));
            emit("tool.completed", { invocationId: intent.invocationId, status: "denied" });
            continue;
          }
        }

        if (!ports.budget.reserve("tool")) return finish("budget_exhausted", "");
        let result: ToolResultRecord;
        try {
          result = await ports.tools.invoke(intent, signal);
        } catch {
          result = {
            invocationId: intent.invocationId,
            status: "failed",
            result: { error: "tool_error" },
          };
        }
        ports.store.saveResult(result);
        emit("tool.completed", { invocationId: intent.invocationId, status: result.status });
        if (result.status === "unknown") return finish("needs_review", "");
      }
      ports.store.saveCheckpoint(
        checkpointFor(checkpoint.turnId, "model", completedIds(ports), []),
      );
      continue;
    }

    const messages = ports.store.messages();
    const last = messages[messages.length - 1];
    if (!last || (!last.text && last.toolIntents.length === 0)) {
      return finish("needs_review", "");
    }
    ports.store.saveCheckpoint(
      checkpointFor(checkpoint.turnId, "model", completedIds(ports), []),
    );
    return finish("completed", last.text);
  }
}

function completedIds(ports: EnginePorts): string[] {
  return ports.store
    .messages()
    .flatMap((message) => message.toolIntents.map((intent) => intent.invocationId))
    .filter((id) => ports.store.hasResult(id));
}

function denied(
  intent: { invocationId: string },
  error: string,
): ToolResultRecord {
  return { invocationId: intent.invocationId, status: "denied", result: { error } };
}
