/**
 * Runtime JSONL v1 codec. CareerLens custom protocol: not ACP, not Pi RPC.
 * stdout carries protocol frames only; diagnostics belong on stderr.
 */
export const MAX_FRAME_BYTES = 64 * 1024;

export class FrameError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "FrameError";
    this.code = code;
  }
}

export interface RequestFrame {
  v: 1;
  type: "request";
  id: string;
  method: string;
  params: Record<string, unknown>;
}

export interface ResponseFrame {
  v: 1;
  type: "response";
  id: string;
  ok: boolean;
  result?: unknown;
  error?: { code: string; message: string };
}

export interface EventFrame {
  v: 1;
  type: "event";
  run_id: string;
  attempt: number;
  runtime_generation: number;
  local_seq: number;
  kind: string;
  payload: Record<string, unknown>;
}

export type RuntimeFrame = RequestFrame | ResponseFrame | EventFrame;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function encodeFrame(frame: RuntimeFrame): string {
  const line = JSON.stringify(frame);
  if (Buffer.byteLength(line, "utf8") > MAX_FRAME_BYTES) {
    throw new FrameError("frame_too_large", "encoded frame exceeds M0 limit");
  }
  if (line.includes("\n") || line.includes("\r")) {
    throw new FrameError("invalid_frame", "frame must be a single LF-terminated line");
  }
  return line;
}

export function decodeFrame(line: string): RuntimeFrame {
  if (line.includes("\r")) {
    throw new FrameError("invalid_frame", "CR is not allowed in a frame");
  }
  if (Buffer.byteLength(line, "utf8") > MAX_FRAME_BYTES) {
    throw new FrameError("frame_too_large", "frame exceeds M0 limit");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    throw new FrameError("invalid_json", "frame is not valid JSON");
  }
  if (!isRecord(parsed) || parsed.v !== 1 || typeof parsed.type !== "string") {
    throw new FrameError("invalid_frame", "frame envelope is invalid");
  }
  if (parsed.type === "request") {
    if (
      typeof parsed.id !== "string" ||
      typeof parsed.method !== "string" ||
      !isRecord(parsed.params)
    ) {
      throw new FrameError("invalid_frame", "request frame is invalid");
    }
    return parsed as unknown as RequestFrame;
  }
  if (parsed.type === "response") {
    if (typeof parsed.id !== "string" || typeof parsed.ok !== "boolean") {
      throw new FrameError("invalid_frame", "response frame is invalid");
    }
    return parsed as unknown as ResponseFrame;
  }
  if (parsed.type === "event") {
    if (
      typeof parsed.run_id !== "string" ||
      typeof parsed.attempt !== "number" ||
      typeof parsed.runtime_generation !== "number" ||
      typeof parsed.local_seq !== "number" ||
      typeof parsed.kind !== "string" ||
      !isRecord(parsed.payload)
    ) {
      throw new FrameError("invalid_frame", "event frame is invalid");
    }
    return parsed as unknown as EventFrame;
  }
  throw new FrameError("unknown_type", "unsupported frame type");
}

/** Streaming decoder: partial lines are buffered, invalid UTF-8 is fatal. */
export class FrameDecoder {
  private buffer = "";
  private decoder = new TextDecoder("utf-8", { fatal: true });

  push(chunk: Uint8Array): string[] {
    const text = this.decoder.decode(chunk, { stream: true });
    this.buffer += text;
    const lines: string[] = [];
    let index = this.buffer.indexOf("\n");
    while (index >= 0) {
      lines.push(this.buffer.slice(0, index));
      this.buffer = this.buffer.slice(index + 1);
      if (Buffer.byteLength(this.buffer, "utf8") > MAX_FRAME_BYTES) {
        throw new FrameError("frame_too_large", "unterminated frame exceeds M0 limit");
      }
      index = this.buffer.indexOf("\n");
    }
    if (Buffer.byteLength(this.buffer, "utf8") > MAX_FRAME_BYTES) {
      throw new FrameError("frame_too_large", "unterminated frame exceeds M0 limit");
    }
    return lines;
  }
}
