const MAX_EVENT_LENGTH = 64 * 1024;

export class RunEventProtocolError extends Error {}

function parseEvent(lines: string[], onData: (event: unknown) => void) {
  const data: string[] = [];
  let id: string | undefined;
  let eventType: string | undefined;
  for (const line of lines) {
    if (line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "data") data.push(value);
    if (field === "id") id = value;
    if (field === "event") eventType = value;
  }
  if (data.length === 0) return;

  let event;
  try {
    event = JSON.parse(data.join("\n"));
  } catch {
    throw new RunEventProtocolError("任务进度收到无效 JSON。");
  }
  if (!event || typeof event !== "object" ||
      typeof event.run_id !== "string" || !event.run_id ||
      !Number.isSafeInteger(event.seq) || event.seq <= 0 ||
      typeof event.event_type !== "string" || !event.event_type ||
      !event.data || typeof event.data !== "object" || Array.isArray(event.data) ||
      (event.generation !== undefined &&
        (!Number.isSafeInteger(event.generation) || event.generation < 0)) ||
      (event.schema_version !== undefined && event.schema_version !== 1) ||
      (id !== undefined && id !== String(event.seq)) ||
      (eventType !== undefined && eventType !== "run" && eventType !== event.event_type)) {
    throw new RunEventProtocolError("任务进度事件格式或序号不一致。");
  }
  onData(event);
}

export async function readRunEvents(
  body: ReadableStream<Uint8Array>,
  onData: (event: unknown) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "";
  let lines: string[] = [];
  let eventLength = 0;

  function consumeLine(line: string) {
    if (!line) {
      parseEvent(lines, onData);
      lines = [];
      eventLength = 0;
    } else {
      eventLength += line.length + 1;
      if (eventLength > MAX_EVENT_LENGTH) {
        throw new RunEventProtocolError("任务进度单条事件过大。");
      }
      lines.push(line);
    }
  }

  function consumeBuffer(eof = false) {
    const separator = /\r\n|\r|\n/g;
    let start = 0;
    for (const match of buffer.matchAll(separator)) {
      const next = match.index + match[0].length;
      if (!eof && match[0] === "\r" && next === buffer.length) break;
      consumeLine(buffer.slice(start, match.index));
      start = next;
    }
    buffer = buffer.slice(start);
    if (buffer.length + eventLength > MAX_EVENT_LENGTH) {
      throw new RunEventProtocolError("任务进度单条事件过大。");
    }
    if (eof) {
      if (buffer) consumeLine(buffer);
      consumeLine("");
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      consumeBuffer();
    }
    buffer += decoder.decode();
    consumeBuffer(true);
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
