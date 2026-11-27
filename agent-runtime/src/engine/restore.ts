import type { SafeCheckpoint } from "./types.ts";

export const CHECKPOINT_SCHEMA_VERSION = 1;
export const M0_ENGINE_VERSION = "0.1.0-m0";

export function isSafeCheckpoint(value: unknown): value is SafeCheckpoint {
  if (typeof value !== "object" || value === null) return false;
  const cp = value as Record<string, unknown>;
  if (cp.schemaVersion !== CHECKPOINT_SCHEMA_VERSION) return false;
  if (cp.engineVersion !== M0_ENGINE_VERSION) return false;
  if (typeof cp.runId !== "string" || typeof cp.sessionId !== "string") return false;
  if (typeof cp.turnId !== "string") return false;
  if (cp.next !== "model" && cp.next !== "tools" && cp.next !== "validate") return false;
  if (!Array.isArray(cp.completedInvocationIds) || !Array.isArray(cp.pendingInvocationIds)) {
    return false;
  }
  return cp.completedInvocationIds.every((id) => typeof id === "string") &&
    cp.pendingInvocationIds.every((id) => typeof id === "string") &&
    typeof cp.messageHeadRef === "string" &&
    typeof cp.budgetRef === "string" &&
    typeof cp.policyRevision === "string" &&
    typeof cp.toolSnapshotRef === "string" &&
    typeof cp.inputRevisionRef === "string";
}

/** Reject old or foreign checkpoints instead of silently executing their intents. */
export function validateCheckpoint(value: unknown): SafeCheckpoint {
  if (!isSafeCheckpoint(value)) {
    throw new Error("unsupported checkpoint schema or engine version");
  }
  return value;
}

export function serializeCheckpoint(checkpoint: SafeCheckpoint): string {
  return JSON.stringify(checkpoint);
}

export function deserializeCheckpoint(raw: string): SafeCheckpoint {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("checkpoint is not valid JSON");
  }
  return validateCheckpoint(parsed);
}
