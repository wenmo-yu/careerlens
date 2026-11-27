/**
 * CareerLens Agent Core port and DTO definitions.
 *
 * M0 prototype only. These types are independent of Pi, ACP, FastAPI, SQLite
 * and every CareerLens business model. They are erasable TypeScript so Node
 * 22 can execute them directly without a build step.
 */

export type StopReason =
  | "completed"
  | "approval_required"
  | "cancelled"
  | "budget_exhausted"
  | "model_error"
  | "tool_error"
  | "interrupted"
  | "needs_review";

export type EnginePhase =
  | "prepare"
  | "model_stream"
  | "tool_plan"
  | "tool_execute"
  | "validate"
  | "settled";

export type SideEffectClass = "read_only" | "write" | "external";
export type ApprovalPolicy = "allow" | "ask" | "deny";

export interface Usage {
  modelTurns: number;
  toolCalls: number;
  inputTokens: number;
  outputTokens: number;
}

export interface ToolDefinition {
  name: string;
  version: string;
  sideEffectClass: SideEffectClass;
  approvalPolicy: ApprovalPolicy;
  description: string;
}

export interface ToolIntent {
  invocationId: string;
  providerCallId: string;
  turnId: string;
  ordinal: number;
  name: string;
  version: string;
  args: unknown;
  argsDigest: string;
}

export type ToolResultStatus = "succeeded" | "failed" | "denied" | "unknown";

export interface ToolResultRecord {
  invocationId: string;
  status: ToolResultStatus;
  result: unknown;
}

export interface AssistantMessage {
  messageId: string;
  turnId: string;
  text: string;
  toolIntents: ToolIntent[];
}

export interface SafeCheckpoint {
  schemaVersion: number;
  engineVersion: string;
  runId: string;
  sessionId: string;
  turnId: string;
  next: "model" | "tools" | "validate";
  messageHeadRef: string;
  completedInvocationIds: string[];
  pendingInvocationIds: string[];
  budgetRef: string;
  policyRevision: string;
  toolSnapshotRef: string;
  inputRevisionRef: string;
}

export interface EngineSpec {
  id: string;
  version: string;
  instructions: string;
  toolIds: readonly string[];
  modelConfigRef: string;
  outputSchemaRef: string;
}

export interface RunInput {
  runId: string;
  sessionId: string;
  goal: string;
  inputRevisionRef: string;
}

export interface ModelRequest {
  turnId: string;
  spec: EngineSpec;
  input: RunInput;
  messages: AssistantMessage[];
  tools: ToolDefinition[];
}

export type ModelDelta =
  | { kind: "text_delta"; text: string }
  | {
      kind: "tool_call_delta";
      index: number;
      name?: string;
      argsChunk?: string;
      providerCallId?: string;
    }
  | { kind: "usage"; inputTokens?: number; outputTokens?: number }
  | { kind: "finish"; reason: string }
  | { kind: "error"; message: string };

export interface ModelCallTool {
  name: string;
  args: unknown;
  providerCallId: string;
  ordinal: number;
}

export interface ModelResponse {
  text: string;
  toolCalls: ModelCallTool[];
  finish: string;
  usage: { inputTokens: number; outputTokens: number };
}

export interface EngineOutcome {
  stopReason: StopReason;
  finalText: string;
  usage: Usage;
  checkpoint?: SafeCheckpoint;
}

export interface ModelPort {
  stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelDelta>;
}

export interface ToolExecutor {
  definitions(): ToolDefinition[];
  invoke(intent: ToolIntent, signal: AbortSignal): Promise<ToolResultRecord>;
}

export interface DurableBoundaryClient {
  saveInput(input: RunInput): void;
  getInput(runId: string): RunInput | undefined;
  appendMessage(message: AssistantMessage): void;
  messages(): AssistantMessage[];
  commitIntents(intents: ToolIntent[]): void;
  pendingIntents(): ToolIntent[];
  hasResult(invocationId: string): boolean;
  getResult(invocationId: string): ToolResultRecord | undefined;
  saveResult(result: ToolResultRecord): void;
  saveCheckpoint(checkpoint: SafeCheckpoint): void;
  getCheckpoint(): SafeCheckpoint | undefined;
}

export interface BudgetSnapshot {
  maxTurns: number;
  turns: number;
  maxToolCalls: number;
  toolCalls: number;
  inputTokens: number;
  outputTokens: number;
}

export interface BudgetClient {
  reserve(kind: "turn" | "tool"): boolean;
  consume(usage: { inputTokens?: number; outputTokens?: number }): void;
  snapshot(): BudgetSnapshot;
}

export interface ApprovalClient {
  request(intent: ToolIntent, digest: string): string;
  approvalFor(invocationId: string): string | undefined;
  digestOf(approvalId: string): string | undefined;
  decision(approvalId: string): "pending" | "approved" | "denied";
  consume(approvalId: string): boolean;
}

export interface EngineEvent {
  kind: string;
  runId: string;
  localSeq: number;
  payload: Record<string, unknown>;
}

export interface EventSink {
  emit(event: EngineEvent): void;
}

export interface EnginePorts {
  model: ModelPort;
  tools: ToolExecutor;
  store: DurableBoundaryClient;
  budget: BudgetClient;
  events: EventSink;
  approvals: ApprovalClient;
}
