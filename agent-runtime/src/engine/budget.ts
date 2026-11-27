import type { BudgetClient, BudgetSnapshot } from "./types.ts";

export interface BudgetLimits {
  maxTurns: number;
  maxToolCalls: number;
  maxInputTokens?: number;
  maxOutputTokens?: number;
}

/**
 * Deterministic in-memory budget for the M0 prototype.
 *
 * Real budgets live in the business store and accumulate across attempts;
 * here the same instance is injected into every attempt so restart tests can
 * prove that counters are not reset.
 */
export class InMemoryBudget implements BudgetClient {
  private state: BudgetSnapshot;
  private limits: BudgetLimits;

  constructor(limits: BudgetLimits, restored?: BudgetSnapshot) {
    this.limits = limits;
    this.state = restored
      ? { ...restored }
      : {
          maxTurns: limits.maxTurns,
          turns: 0,
          maxToolCalls: limits.maxToolCalls,
          toolCalls: 0,
          inputTokens: 0,
          outputTokens: 0,
        };
  }

  reserve(kind: "turn" | "tool"): boolean {
    if (kind === "turn") {
      if (this.state.turns >= this.limits.maxTurns) return false;
      this.state.turns += 1;
      return true;
    }
    if (this.state.toolCalls >= this.limits.maxToolCalls) return false;
    this.state.toolCalls += 1;
    return true;
  }

  consume(usage: { inputTokens?: number; outputTokens?: number }): void {
    this.state.inputTokens += usage.inputTokens ?? 0;
    this.state.outputTokens += usage.outputTokens ?? 0;
  }

  snapshot(): BudgetSnapshot {
    return { ...this.state };
  }

  exhaustedByTokens(): boolean {
    const inputLimit = this.limits.maxInputTokens ?? Number.POSITIVE_INFINITY;
    const outputLimit = this.limits.maxOutputTokens ?? Number.POSITIVE_INFINITY;
    return this.state.inputTokens > inputLimit || this.state.outputTokens > outputLimit;
  }
}
