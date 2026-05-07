/**
 * Tests for the SSE wire-format reader. We mock `fetch` to return a
 * hand-crafted ReadableStream and verify the async iterator yields one
 * `{event, data}` per blank-line-terminated block.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { postSSE } from "@/api/sse";

function streamFrom(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function mockFetch(body: ReadableStream<Uint8Array>, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? "OK" : "Error",
    body,
  });
}

describe("postSSE", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.useRealTimers();
  });

  it("yields one event per block", async () => {
    const body = streamFrom(
      "event: text_delta\n",
      'data: {"text":"Hello"}\n',
      "\n",
      "event: text_delta\n",
      'data: {"text":" world"}\n',
      "\n",
      "event: done\n",
      'data: {"proposal_ids":[]}\n\n',
    );
    globalThis.fetch = mockFetch(body) as typeof fetch;

    const events: { event: string; data: unknown }[] = [];
    for await (const evt of postSSE<Record<string, unknown>>("/api/v1/chat/stream", {})) {
      events.push(evt);
    }

    expect(events).toEqual([
      { event: "text_delta", data: { text: "Hello" } },
      { event: "text_delta", data: { text: " world" } },
      { event: "done", data: { proposal_ids: [] } },
    ]);
  });

  it("handles a single chunk that contains multiple events", async () => {
    const body = streamFrom(
      ["event: a", 'data: {"k":1}', "", "event: b", 'data: {"k":2}', "", ""].join("\n"),
    );
    globalThis.fetch = mockFetch(body) as typeof fetch;

    const events = [];
    for await (const evt of postSSE("/p", {})) events.push(evt);
    expect(events.map((e) => e.event)).toEqual(["a", "b"]);
  });

  it("flushes a trailing block missing the double newline", async () => {
    const body = streamFrom('event: x\ndata: {"v":42}\n');
    globalThis.fetch = mockFetch(body) as typeof fetch;
    const events = [];
    for await (const evt of postSSE("/p", {})) events.push(evt);
    expect(events).toEqual([{ event: "x", data: { v: 42 } }]);
  });

  it("treats non-JSON data as a string", async () => {
    const body = streamFrom("event: ping\ndata: hello\n\n");
    globalThis.fetch = mockFetch(body) as typeof fetch;
    const events = [];
    for await (const evt of postSSE("/p", {})) events.push(evt);
    expect(events).toEqual([{ event: "ping", data: "hello" }]);
  });

  it("throws on non-2xx", async () => {
    const body = streamFrom("");
    globalThis.fetch = mockFetch(body, false) as typeof fetch;
    await expect(async () => {
      for await (const _ of postSSE("/p", {})) {
        // pragma: no consume
      }
    }).rejects.toThrow(/SSE request failed/);
  });
});
