/**
 * Chat streaming hook. POSTs to `/api/v1/chat/stream`, reads SSE events,
 * and translates them into local React state suitable for rendering.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { postSSE } from "@/api/sse";

export type ToolCall = {
  id: string;
  name: string;
  status: "running" | "ok" | "error";
  input?: unknown;
  output?: unknown;
};

export type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
  toolCalls?: ToolCall[];
  proposalIds?: string[];
};

const TREE_ID = "00000000-0000-0000-0000-000000000000";

type SseEventData = Record<string, unknown> & { text?: string };

export function useChatStream() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight request on unmount.
  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      const userTurn: ChatTurn = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };
      const pendingId = crypto.randomUUID();
      const pending: ChatTurn = {
        id: pendingId,
        role: "assistant",
        content: "",
        pending: true,
        toolCalls: [],
        proposalIds: [],
      };

      setTurns((prev) => {
        const history = prev.filter((t) => !t.pending && !t.error);
        const next = [...history, userTurn, pending];
        return next;
      });

      const history = turns
        .filter((t) => !t.pending && !t.error)
        .map((t) => ({ role: t.role, content: t.content }));

      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const evt of postSSE<SseEventData>(
          "/api/v1/chat/stream",
          {
            tree_id: TREE_ID,
            message: trimmed,
            history,
          },
          { signal: controller.signal },
        )) {
          setTurns((prev) =>
            prev.map((t) => (t.id === pendingId ? applyEvent(t, evt.event, evt.data) : t)),
          );
        }
      } catch (e) {
        if ((e as { name?: string }).name === "AbortError") {
          setTurns((prev) =>
            prev.map((t) =>
              t.id === pendingId
                ? { ...t, pending: false, content: t.content || "(cancelled)" }
                : t,
            ),
          );
        } else {
          const message = (e as { message?: string }).message ?? String(e);
          setTurns((prev) =>
            prev.map((t) =>
              t.id === pendingId
                ? { ...t, pending: false, error: true, content: `Error: ${message}` }
                : t,
            ),
          );
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
        // Mark pending false defensively in case the stream ended without a `done` event.
        setTurns((prev) => prev.map((t) => (t.id === pendingId ? { ...t, pending: false } : t)));
      }
    },
    [busy, turns],
  );

  return { turns, busy, send, stop };
}

function applyEvent(turn: ChatTurn, type: string, data: SseEventData): ChatTurn {
  switch (type) {
    case "text_delta": {
      const text = String(data?.text ?? "");
      return { ...turn, content: turn.content + text };
    }
    case "tool_use_started": {
      const id = String(data?.id ?? "");
      const name = String(data?.name ?? "tool");
      const calls = [...(turn.toolCalls ?? []), { id, name, status: "running" as const }];
      return { ...turn, toolCalls: calls };
    }
    case "tool_use_finished": {
      const id = String(data?.id ?? "");
      return {
        ...turn,
        toolCalls: (turn.toolCalls ?? []).map((c) =>
          c.id === id ? { ...c, input: data?.input } : c,
        ),
      };
    }
    case "tool_result": {
      const id = String((data as { tool_use_id?: string })?.tool_use_id ?? "");
      const isError = Boolean((data as { is_error?: boolean })?.is_error);
      return {
        ...turn,
        toolCalls: (turn.toolCalls ?? []).map((c) =>
          c.id === id
            ? {
                ...c,
                status: isError ? "error" : "ok",
                output: (data as { output?: unknown })?.output,
              }
            : c,
        ),
      };
    }
    case "done": {
      const proposalIds = ((data as { proposal_ids?: string[] })?.proposal_ids ?? []).map(String);
      return { ...turn, pending: false, proposalIds };
    }
    case "error": {
      const message = String((data as { message?: string })?.message ?? "unknown error");
      return { ...turn, pending: false, error: true, content: turn.content || `Error: ${message}` };
    }
    case "start":
    case "usage":
    case "thinking_delta":
    default:
      return turn;
  }
}
