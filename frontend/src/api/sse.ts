/**
 * Tiny POST-then-SSE reader. EventSource only supports GET, so we use fetch
 * + ReadableStream and parse the text/event-stream wire format ourselves.
 *
 * Wire format (per the SSE spec):
 *
 *   event: <type>\n
 *   data:  <json>\n
 *   \n
 *
 * Multiple `data:` lines per event are concatenated with newlines. We yield
 * one `{ event, data }` object per blank-line-terminated block.
 */

import { env } from "@/lib/env";

export type SseEvent<TData = unknown> = {
  event: string;
  data: TData;
};

export async function* postSSE<TData = unknown>(
  path: string,
  body: unknown,
  options: { signal?: AbortSignal; requestId?: string } = {},
): AsyncIterableIterator<SseEvent<TData>> {
  const requestId = options.requestId ?? crypto.randomUUID();
  const response = await fetch(`${env.VITE_API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Request-ID": requestId,
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status} ${response.statusText}`);
  }
  if (!response.body) {
    throw new Error("SSE response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // SSE chunks must be consumed strictly in order; sequential await is intentional.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let blockEnd: number;
    while ((blockEnd = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, blockEnd);
      buffer = buffer.slice(blockEnd + 2);
      const parsed = parseEventBlock<TData>(block);
      if (parsed) yield parsed;
    }
  }

  // Flush any final block (some servers omit the trailing newline).
  if (buffer.trim().length > 0) {
    const parsed = parseEventBlock<TData>(buffer);
    if (parsed) yield parsed;
  }
}

function parseEventBlock<TData>(block: string): SseEvent<TData> | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
    // ignore other field types (id, retry); not used here
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  let data: TData;
  try {
    data = JSON.parse(raw) as TData;
  } catch {
    data = raw as unknown as TData;
  }
  return { event, data };
}
