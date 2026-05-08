/**
 * Tests that ChatStreamProvider's `send` builds the correct wire body when
 * called with attachments: the message stays clean (no bracket prefix), the
 * attachments travel as structured `attachments: [{document_id}]` entries,
 * and the optimistic user turn carries the attachment refs so the bubble can
 * render an inline image preview while the server replies.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/sse", () => ({
  postSSE: vi.fn(),
}));

vi.mock("@/api/endpoints/conversations", () => ({
  fetchConversation: vi.fn().mockResolvedValue({ id: "conv-1", messages: [] }),
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { act, render } from "@testing-library/react";
import * as React from "react";

import { postSSE } from "@/api/sse";
import {
  ChatStreamProvider,
  useChatStream,
  type ChatStreamValue,
} from "@/features/chat/ChatStreamProvider";

function setupApp() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const captured: { current: ChatStreamValue | null } = { current: null };

  function Capture() {
    captured.current = useChatStream();
    return null;
  }

  const rootRoute = createRootRoute({
    component: () =>
      React.createElement(
        QueryClientProvider,
        { client: qc },
        React.createElement(
          ChatStreamProvider,
          null,
          React.createElement(Capture),
          React.createElement(Outlet),
        ),
      ),
  });
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => null,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });

  return { router, captured };
}

describe("ChatStreamProvider.send with attachments", () => {
  beforeEach(() => {
    (postSSE as unknown as ReturnType<typeof vi.fn>).mockReset();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("sends attachments as a structured field and keeps the message clean", async () => {
    const captured: { body?: Record<string, unknown> } = {};
    (postSSE as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (_path: string, body: Record<string, unknown>) => {
        captured.body = body;
        return (async function* () {
          yield { event: "start", data: { conversation_id: "c-1", agent_run_id: "r-1" } };
          yield { event: "done", data: { proposal_ids: [] } };
        })();
      },
    );

    const { router, captured: hookRef } = setupApp();
    render(React.createElement(RouterProvider, { router }));
    await act(async () => {
      await Promise.resolve();
    });
    const stream = hookRef.current;
    if (!stream) throw new Error("ChatStreamProvider did not capture");

    await act(async () => {
      await stream.send("hello", [
        { documentId: "doc-1", filename: "scan.pdf" },
        { documentId: "doc-2", filename: "tree.png", mimeType: "image/png", kind: "image" },
      ]);
    });

    const body = captured.body;
    if (!body) throw new Error("postSSE was not called");
    expect(body.message).toBe("hello");
    expect(body.attachments).toEqual([{ document_id: "doc-1" }, { document_id: "doc-2" }]);
    // The legacy `history` field is gone; the server reloads from the DB.
    expect("history" in body).toBe(false);

    const updated = hookRef.current;
    if (!updated) throw new Error("ChatStreamProvider lost capture after send");
    const userTurn = updated.turns.find((t) => t.role === "user");
    expect(userTurn?.content).toBe("hello");
    expect(userTurn?.attachments?.map((a) => a.documentId)).toEqual(["doc-1", "doc-2"]);
  });

  it("omits attachments from the body when the user sent none", async () => {
    const captured: { body?: Record<string, unknown> } = {};
    (postSSE as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (_path: string, body: Record<string, unknown>) => {
        captured.body = body;
        return (async function* () {
          yield { event: "start", data: { conversation_id: "c-1", agent_run_id: "r-1" } };
          yield { event: "done", data: { proposal_ids: [] } };
        })();
      },
    );

    const { router, captured: hookRef } = setupApp();
    render(React.createElement(RouterProvider, { router }));
    await act(async () => {
      await Promise.resolve();
    });
    const stream = hookRef.current;
    if (!stream) throw new Error("ChatStreamProvider did not capture");

    await act(async () => {
      await stream.send("just text");
    });

    const body = captured.body;
    if (!body) throw new Error("postSSE was not called");
    expect(body.message).toBe("just text");
    expect(body.attachments).toEqual([]);
  });
});
