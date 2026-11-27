/**
 * Runtime JSONL v1 method registry.
 *
 * Mirrors `contracts/runtime-jsonl-v1.methods.json`. Keep both in sync:
 * the JSON file is the published contract, this module is the enforcement
 * point inside the CLI-side host.
 */

export type ErrorCode =
  | "invalid_frame"
  | "invalid_json"
  | "frame_too_large"
  | "unknown_type"
  | "invalid_id_space"
  | "unknown_method"
  | "invalid_params"
  | "duplicate_request"
  | "run_busy"
  | "handler_error"
  | "runtime_closed";

export interface RuntimeErrorBody {
  code: ErrorCode;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export interface MethodSpec {
  name: string;
  direction: "scheduler_to_runtime" | "runtime_to_scheduler";
  idSpace: "s" | "c";
  requiredParams: string[];
  optionalParams: string[];
  idempotent: boolean;
}

const SPECS: MethodSpec[] = [
  {
    name: "runtime.bind",
    direction: "scheduler_to_runtime",
    idSpace: "s",
    requiredParams: ["session_id"],
    optionalParams: ["run_id"],
    idempotent: true,
  },
  {
    name: "runtime.ping",
    direction: "scheduler_to_runtime",
    idSpace: "s",
    requiredParams: [],
    optionalParams: [],
    idempotent: true,
  },
  {
    name: "run.start",
    direction: "scheduler_to_runtime",
    idSpace: "s",
    requiredParams: ["run_id"],
    optionalParams: ["attempt", "runtime_generation", "goal"],
    idempotent: false,
  },
  {
    name: "run.cancel",
    direction: "scheduler_to_runtime",
    idSpace: "s",
    requiredParams: [],
    optionalParams: ["run_id"],
    idempotent: true,
  },
  {
    name: "gateway.invoke",
    direction: "runtime_to_scheduler",
    idSpace: "c",
    requiredParams: ["tool"],
    optionalParams: ["run_id", "args"],
    idempotent: false,
  },
];

export const METHODS: ReadonlyMap<string, MethodSpec> = new Map(
  SPECS.map((spec) => [spec.name, spec]),
);

export const RETRYABLE: Readonly<Record<ErrorCode, boolean>> = {
  invalid_frame: false,
  invalid_json: false,
  frame_too_large: false,
  unknown_type: false,
  invalid_id_space: false,
  unknown_method: false,
  invalid_params: false,
  duplicate_request: false,
  run_busy: true,
  handler_error: false,
  runtime_closed: true,
};

export function lookupMethod(name: string): MethodSpec | undefined {
  return METHODS.get(name);
}

/** Returns the required parameter names that are missing or empty. */
export function missingParams(spec: MethodSpec, params: Record<string, unknown>): string[] {
  return spec.requiredParams.filter((key) => {
    const value = params[key];
    if (value === undefined || value === null) return true;
    if (typeof value === "string" && value.length === 0) return true;
    return false;
  });
}

export function runtimeError(
  code: ErrorCode,
  message: string,
  details?: Record<string, unknown>,
): RuntimeErrorBody {
  const body: RuntimeErrorBody = { code, message, retryable: RETRYABLE[code] };
  if (details) body.details = details;
  return body;
}

/** Bounded duplicate-id tracker: keeps memory flat on long sessions. */
export class SeenRequestIds {
  private order: string[] = [];
  private seen = new Set<string>();
  private limit: number;

  constructor(limit = 512) {
    this.limit = limit;
  }

  has(id: string): boolean {
    return this.seen.has(id);
  }

  add(id: string): void {
    if (this.seen.has(id)) return;
    this.seen.add(id);
    this.order.push(id);
    while (this.order.length > this.limit) {
      const oldest = this.order.shift();
      if (oldest !== undefined) this.seen.delete(oldest);
    }
  }
}
