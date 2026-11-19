export async function readRunEvents(
  body: ReadableStream<Uint8Array>,
  onData: (event: unknown) => void,
) {
  // Decode chunks manually instead of TextDecoderStream: the latter's
  // writable side is typed WritableStream<BufferSource>, which no longer
  // satisfies pipeThrough's ReadableWritablePair<string, Uint8Array> under
  // TypeScript's stricter Uint8Array<ArrayBufferLike> generic. TextDecoder
  // with { stream: true } keeps multi-byte UTF-8 sequences correct across
  // chunk boundaries and is type-safe here.
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = /\r?\n\r?\n/.exec(buffer);
      while (boundary) {
        const packet = buffer.slice(0, boundary.index);
        const lines = packet.split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""));
        if (lines.length) onData(JSON.parse(lines.join("\n")));
        buffer = buffer.slice(boundary.index + boundary[0].length);
        boundary = /\r?\n\r?\n/.exec(buffer);
      }
      if (buffer.length > 64 * 1024) throw new Error("任务进度单条事件过大");
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
