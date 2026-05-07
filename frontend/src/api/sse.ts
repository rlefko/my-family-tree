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
 * sse-starlette and most servers terminate lines with CRLF, so this parser
 * normalises every chunk to plain `\n` before splitting on `\n\n` blocks.
 * Multiple `data:` lines per event are concatenated with newlines. We yield
 * one `{ event, data }` object per blank-line-terminated block.
 */

import { env } from "@/lib/env";

export type SseEvent<TData = unknown> = {
  event: string;
  data: TData;
};

const DEBUG = typeof import.meta !== "undefined" && import.meta.env?.DEV;

export async function* postSSE<TData = unknown>(
  path: string,
  body: unknown,
  options: { signal?: AbortSignal; requestId?: string } = {},
): AsyncIterableIterator<SseEvent<TData>> {
  const requestId = options.requestId ?? crypto.randomUUID();
  const url = `${env.VITE_API_BASE_URL}${path}`;
  if (DEBUG) console.debug("[sse] POST", url, body);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Request-ID": requestId,
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = "";
    try {
      detail = await response.text();
    } catch {
      // ignore
    }
    throw new Error(
      `SSE request failed: ${response.status} ${response.statusText}${detail ? ` — ${detail.slice(0, 200)}` : ""}`,
    );
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
    // Normalise CRLF → LF so downstream block-splitting on \n\n is reliable
    // regardless of which server transport we're talking to.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    let blockEnd: number;
    while ((blockEnd = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, blockEnd);
      buffer = buffer.slice(blockEnd + 2);
      const parsed = parseEventBlock<TData>(block);
      if (parsed) {
        if (DEBUG) console.debug("[sse]", parsed.event, parsed.data);
        yield parsed;
      }
    }
  }

  // Flush any final block (some servers omit the trailing newline).
  if (buffer.trim().length > 0) {
    const parsed = parseEventBlock<TData>(buffer);
    if (parsed) {
      if (DEBUG) console.debug("[sse]", parsed.event, parsed.data);
      yield parsed;
    }
  }
  if (DEBUG) console.debug("[sse] stream ended");
}

function parseEventBlock<TData>(block: string): SseEvent<TData> | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
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
