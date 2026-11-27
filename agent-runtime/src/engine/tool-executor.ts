import type { ToolDefinition, ToolExecutor, ToolIntent, ToolResultRecord } from "./types.ts";

export type ToolHandler = (
  args: unknown,
  signal: AbortSignal,
) => unknown | Promise<unknown>;

/**
 * Prototype tool gateway. The M0 scope only exposes synthetic read-only tools;
 * there are no coding tools, no credentials and no file/network access here.
 */
export class ToolGateway implements ToolExecutor {
  private defs: ToolDefinition[];
  private handlers: Map<string, ToolHandler>;

  constructor(definitions: ToolDefinition[], handlers: Record<string, ToolHandler>) {
    this.defs = definitions;
    this.handlers = new Map(Object.entries(handlers));
  }

  definitions(): ToolDefinition[] {
    return this.defs;
  }

  async invoke(intent: ToolIntent, signal: AbortSignal): Promise<ToolResultRecord> {
    const def = this.defs.find(
      (item) => item.name === intent.name && item.version === intent.version,
    );
    if (!def || !this.handlers.has(intent.name)) {
      return {
        invocationId: intent.invocationId,
        status: "failed",
        result: { error: "unknown_tool", name: intent.name, version: intent.version },
      };
    }
    if (signal.aborted) {
      return {
        invocationId: intent.invocationId,
        status: "unknown",
        result: { error: "cancelled_before_start" },
      };
    }
    try {
      const result = await this.handlers.get(intent.name)?.(intent.args, signal);
      return { invocationId: intent.invocationId, status: "succeeded", result };
    } catch (error) {
      return {
        invocationId: intent.invocationId,
        status: "failed",
        result: {
          error: "tool_error",
          message: error instanceof Error ? error.message : String(error),
        },
      };
    }
  }
}
