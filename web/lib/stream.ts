import { eventSchema, type RunEvent } from "./types";

export async function* readEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<RunEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 3_000_000)
        throw new Error("Research response exceeded its size limit.");
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      if (done && buffer.trim()) {
        lines.push(buffer);
        buffer = "";
      }
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = eventSchema.parse(JSON.parse(line));
        if (event.type === "result" || event.type === "error") terminal = true;
        yield event;
      }
      if (done) break;
    }
    if (!terminal)
      throw new Error(
        "The research stream ended before a result arrived. Try again.",
      );
  } finally {
    try {
      await reader.cancel();
    } finally {
      reader.releaseLock();
    }
  }
}
