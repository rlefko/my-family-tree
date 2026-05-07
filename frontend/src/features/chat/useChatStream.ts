/**
 * Chat streaming hook. POSTs to `/api/v1/chat/stream`, reads SSE events,
 * and translates them into local React state suitable for rendering.
 *
 * On mount, the hook checks `localStorage` for the active conversation id;
 * if present, it fetches the persisted messages from
 * `GET /api/v1/conversations/{id}` and rehydrates the turn list so a page
 * refresh restores the thread. The first `start` SSE event tells us which
 * conversation we're in (the backend creates one when the client doesn't
 * pass one); we capture it, store it, and echo it on every subsequent
 * request so all turns share the same Conversation row.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchConversation, type AssistantBlock, type MessageRow } from "@/api/endpoints/conversations";
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
const STORAGE_KEY = "mft.activeConversation";

type SseEventData = Record<string, unknown> & { text?: string };

function readStoredConversationId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeConversationId(id: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (id === null) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, id);
    }
  } catch {
    // localStorage may be disabled (private mode); fail silently.
  }
}

function turnsFromMessages(messages: MessageRow[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      const text = m.content
        .map((b) => (b.type === "text" ? b.text : ""))
        .join("");
      turns.push({ id: m.id, role: "user", content: text });
    } else if (m.role === "assistant") {
      const turn: ChatTurn = {
        id: m.id,
        role: "assistant",
        content: "",
        toolCalls: [],
        proposalIds: [],
      };
      for (const block of m.content as AssistantBlock[]) {
        if (block.type === "text") {
          turn.content += block.text;
        } else if (block.type === "tool_use") {
          turn.toolCalls = [
            ...(turn.toolCalls ?? []),
            {
              id: block.id,
              name: block.name,
              status: block.is_error ? "error" : "ok",
              input: block.input,
              output: block.output,
            },
          ];
        } else if (block.type === "proposals_summary") {
          turn.proposalIds = [...(turn.proposalIds ?? []), ...block.proposal_ids];
        }
      }
      turns.push(turn);
    }
  }
  return turns;
}

export function useChatStream() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(() =>
    readStoredConversationId(),
  );
  const conversationIdRef = useRef<string | null>(conversationId);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);
  const userInteractedRef = useRef(false);

  // On mount, hydrate the previously-active conversation from the server.
  // The fetch is async, so we guard against three races: (a) the component
  // unmounts mid-fetch (cancelled flag); (b) the user starts typing/sending
  // while the fetch is in flight (userInteractedRef short-circuits the apply);
  // (c) the rehydrate completes AFTER the user has already received some
  // events for a new turn (we only setTurns when the local list is still
  // empty so we never clobber in-flight state).
  useEffect(() => {
    const id = conversationIdRef.current;
    if (!id || restoredRef.current) return;
    restoredRef.current = true;
    let cancelled = false;
    (async () => {
      try {
        const detail = await fetchConversation(id);
        if (cancelled || userInteractedRef.current) return;
        const restored = turnsFromMessages(detail.messages);
        setTurns((prev) => (prev.length === 0 ? restored : prev));
      } catch {
        if (cancelled) return;
        // Stale or deleted conversation; reset so the next send creates a
        // fresh thread instead of stamping onto a server-side ghost.
        conversationIdRef.current = null;
        setConversationId(null);
        storeConversationId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    conversationIdRef.current = null;
    setConversationId(null);
    storeConversationId(null);
    setTurns([]);
    restoredRef.current = true; // prevent re-hydrating on next render
    userInteractedRef.current = true;
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      userInteractedRef.current = true;

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
        return [...history, userTurn, pending];
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
            conversation_id: conversationIdRef.current,
          },
          { signal: controller.signal },
        )) {
          if (evt.event === "start") {
            const cid = (evt.data as { conversation_id?: string })?.conversation_id;
            if (cid && cid !== conversationIdRef.current) {
              conversationIdRef.current = cid;
              setConversationId(cid);
              storeConversationId(cid);
            }
          }
          setTurns((prev) => {
            const idx = prev.findIndex((t) => t.id === pendingId);
            if (idx === -1) {
              // The pending turn was wiped (e.g., navigating mid-stream or a
              // late rehydrate clobbered state). Re-insert it so subsequent
              // events still have a place to land.
              const recovered: ChatTurn = applyEvent(
                {
                  id: pendingId,
                  role: "assistant",
                  content: "",
                  pending: true,
                  toolCalls: [],
                  proposalIds: [],
                },
                evt.event,
                evt.data,
              );
              return [...prev, recovered];
            }
            const next = prev.slice();
            next[idx] = applyEvent(prev[idx], evt.event, evt.data);
            return next;
          });
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

  return { turns, busy, send, stop, newChat, conversationId };
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
          c.id === id ? { ...c, input: data?.input ?? c.input } : c,
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
