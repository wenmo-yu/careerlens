import type { ModelDelta, ModelResponse } from "./types.ts";

const MAX_ARGS_BYTES = 64 * 1024;
const MAX_TOOL_CALLS = 8;

export class ModelStreamError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ModelStreamError";
    this.code = code;
  }
}

interface AssemblingCall {
  name: string | undefined;
  providerCallId: string | undefined;
  chunks: string[];
  seenChunks: Set<string>;
}

/**
 * Assemble a complete model response from normalized deltas.
 *
 * No tool call is returned unless the stream finished normally and every
 * argument JSON parsed successfully. Partial text is ignored for execution.
 */
export async function collectModelStream(
  deltas: AsyncIterable<ModelDelta>,
  signal: AbortSignal,
): Promise<ModelResponse> {
  let text = "";
  const calls = new Map<number, AssemblingCall>();
  let finish: string | undefined;
  let inputTokens = 0;
  let outputTokens = 0;

  for await (const delta of deltas) {
    if (signal.aborted) {
      throw new ModelStreamError("cancelled", "aborted while reading model stream");
    }
    if (delta.kind === "text_delta") {
      text += delta.text;
    } else if (delta.kind === "tool_call_delta") {
      if (!Number.isInteger(delta.index) || delta.index < 0 || delta.index >= MAX_TOOL_CALLS) {
        throw new ModelStreamError("invalid_delta", "tool call index out of range");
      }
      const existing = calls.get(delta.index) ?? {
        name: undefined,
        providerCallId: undefined,
        chunks: [],
        seenChunks: new Set<string>(),
      };
      if (delta.name !== undefined) {
        if (existing.name !== undefined && existing.name !== delta.name) {
          throw new ModelStreamError("invalid_delta", "conflicting tool name in delta");
        }
        existing.name = delta.name;
      }
      if (delta.providerCallId !== undefined) {
        if (
          existing.providerCallId !== undefined &&
          existing.providerCallId !== delta.providerCallId
        ) {
          throw new ModelStreamError("invalid_delta", "conflicting provider call id");
        }
        existing.providerCallId = delta.providerCallId;
      }
      if (delta.argsChunk !== undefined) {
        // Replayed identical chunks must not duplicate JSON. Conflicting
        // chunks for the same slot are a protocol error, never a retry hint.
        if (!existing.seenChunks.has(delta.argsChunk)) {
          existing.seenChunks.add(delta.argsChunk);
          existing.chunks.push(delta.argsChunk);
        }
        const bytes = existing.chunks.reduce((n, chunk) => n + Buffer.byteLength(chunk), 0);
        if (bytes > MAX_ARGS_BYTES) {
          throw new ModelStreamError("frame_too_large", "tool arguments exceed M0 limit");
        }
      }
      calls.set(delta.index, existing);
    } else if (delta.kind === "usage") {
      inputTokens += delta.inputTokens ?? 0;
      outputTokens += delta.outputTokens ?? 0;
    } else if (delta.kind === "finish") {
      if (finish !== undefined) {
        throw new ModelStreamError("invalid_delta", "duplicate finish delta");
      }
      finish = delta.reason;
    } else if (delta.kind === "error") {
      throw new ModelStreamError("model_error", delta.message);
    }
  }

  if (signal.aborted) {
    throw new ModelStreamError("cancelled", "aborted before stream completion");
  }
  if (finish === undefined) {
    throw new ModelStreamError("truncated", "stream ended without a finish delta");
  }

  const toolCalls = [...calls.entries()]
    .sort(([a], [b]) => a - b)
    .map(([index, call]) => {
      if (!call.name || !call.providerCallId) {
        throw new ModelStreamError("invalid_tool_call", "missing name or provider call id");
      }
      let args: unknown;
      try {
        args = JSON.parse(call.chunks.join(""));
      } catch {
        throw new ModelStreamError("invalid_json", "tool arguments are not valid JSON");
      }
      return { name: call.name, args, providerCallId: call.providerCallId, ordinal: index };
    });

  if (toolCalls.length > 0 && finish !== "tool_calls") {
    throw new ModelStreamError("invalid_finish", "tool calls require finish=tool_calls");
  }
  if (toolCalls.length === 0 && finish !== "stop") {
    throw new ModelStreamError("invalid_finish", "text-only response requires finish=stop");
  }

  return { text, toolCalls, finish, usage: { inputTokens, outputTokens } };
}
