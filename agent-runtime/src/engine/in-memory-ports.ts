import { createHash } from "node:crypto";
import type {
  ApprovalClient,
  AssistantMessage,
  DurableBoundaryClient,
  EngineEvent,
  EventSink,
  ModelDelta,
  ModelPort,
  ModelRequest,
  RunInput,
  SafeCheckpoint,
  ToolIntent,
  ToolResultRecord,
} from "./types.ts";

export function digestArgs(args: unknown): string {
  return createHash("sha256").update(JSON.stringify(args) ?? "null").digest("hex");
}

export class InMemoryStore implements DurableBoundaryClient {
  private inputs = new Map<string, RunInput>();
  private messageList: AssistantMessage[] = [];
  private intents: ToolIntent[] = [];
  private results = new Map<string, ToolResultRecord>();
  private checkpoint: SafeCheckpoint | undefined;

  saveInput(input: RunInput): void {
    this.inputs.set(input.runId, input);
  }

  getInput(runId: string): RunInput | undefined {
    return this.inputs.get(runId);
  }

  appendMessage(message: AssistantMessage): void {
    this.messageList.push(message);
  }

  messages(): AssistantMessage[] {
    return this.messageList.map((message) => ({ ...message }));
  }

  commitIntents(intents: ToolIntent[]): void {
    for (const intent of intents) {
      if (!this.intents.some((item) => item.invocationId === intent.invocationId)) {
        this.intents.push(intent);
      }
    }
  }

  pendingIntents(): ToolIntent[] {
    return this.intents.filter((intent) => !this.results.has(intent.invocationId));
  }

  hasResult(invocationId: string): boolean {
    return this.results.has(invocationId);
  }

  getResult(invocationId: string): ToolResultRecord | undefined {
    return this.results.get(invocationId);
  }

  saveResult(result: ToolResultRecord): void {
    this.results.set(result.invocationId, result);
  }

  saveCheckpoint(checkpoint: SafeCheckpoint): void {
    this.checkpoint = checkpoint;
  }

  getCheckpoint(): SafeCheckpoint | undefined {
    return this.checkpoint;
  }
}

export class InMemoryApprovals implements ApprovalClient {
  private ids = new Map<string, string>();
  private decisions = new Map<string, "pending" | "approved" | "denied">();
  private digests = new Map<string, string>();
  private consumed = new Set<string>();

  request(intent: ToolIntent, digest: string): string {
    const existing = this.ids.get(intent.invocationId);
    if (existing) return existing;
    const id = `approval-${intent.invocationId}`;
    this.ids.set(intent.invocationId, id);
    this.decisions.set(id, "pending");
    this.digests.set(id, digest);
    return id;
  }

  approvalFor(invocationId: string): string | undefined {
    return this.ids.get(invocationId);
  }

  digestOf(approvalId: string): string | undefined {
    return this.digests.get(approvalId);
  }

  decide(approvalId: string, decision: "approved" | "denied"): void {
    if (this.decisions.has(approvalId)) {
      this.decisions.set(approvalId, decision);
    }
  }

  decision(approvalId: string): "pending" | "approved" | "denied" {
    return this.decisions.get(approvalId) ?? "pending";
  }

  consume(approvalId: string): boolean {
    if (this.decision(approvalId) !== "approved" || this.consumed.has(approvalId)) return false;
    this.consumed.add(approvalId);
    return true;
  }
}

export class CollectingEvents implements EventSink {
  events: EngineEvent[] = [];

  emit(event: EngineEvent): void {
    this.events.push(event);
  }
}

export interface ScriptedTurn {
  deltas: ModelDelta[];
  /** Emit one delta per macrotask so cancellation can interleave. */
  delayMs?: number;
}

/**
 * Deterministic model double. Turns are selected by the number of already
 * committed assistant messages, so a resumed attempt does not replay an old
 * model turn.
 */
export class ScriptedModel implements ModelPort {
  turns: ScriptedTurn[];
  requests: ModelRequest[] = [];

  constructor(turns: ScriptedTurn[]) {
    this.turns = turns;
  }

  async *stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelDelta> {
    this.requests.push(request);
    const turn = this.turns[request.messages.length] ?? {
      deltas: [{ kind: "text_delta", text: "" }, { kind: "finish", reason: "stop" }],
    };
    for (const delta of turn.deltas) {
      if (signal.aborted) return;
      if (turn.delayMs) {
        await new Promise<void>((resolve) => setTimeout(resolve, turn.delayMs));
      }
      if (signal.aborted) return;
      yield delta;
    }
  }
}
