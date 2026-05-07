/**
 * Chat streaming hook. POSTs to `/api/v1/chat/stream`, reads SSE events,
 * and translates them into local React state suitable for rendering.
 *
 * On mount, the hook checks `localStorage` for the active conversation id;
 * if present, it fetches the persisted messages from
 * `GET /api/v1/conversations/{id}` and rehydrates the turn list so a page
 * refresh / tab navigation restores the thread. The first `start` SSE event
 * tells us which conversation we're in (the backend creates one when the
 * client doesn't pass one); we capture it, store it, and echo it on every
 * subsequent request so all turns share the same Conversation row.
 *
 * Thinking surface: OpenAI Responses-API reasoning summaries arrive as
 * `thinking_delta` events. We accumulate them on the pending turn so the
 * UI can render a "Thinking..." pill that updates as the model deliberates.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchConversation,
  type AssistantBlock,
  type MessageRow,
} from "@/api/endpoints/conversations";
import { postSSE } from "@/api/sse";

const DEBUG = typeof import.meta !== "undefined" && import.meta.env?.DEV;

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
  thinking?: string;
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
      const text = m.content.map((b) => (b.type === "text" ? b.text : "")).join("");
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
  const qc = useQueryClient();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(() =>
    readStoredConversationId(),
  );
  const conversationIdRef = useRef<string | null>(conversationId);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);
  const userInteractedRef = useRef(false);

  // Hydrate the previously-active conversation from the server. Three races
  // to defend against:
  // (a) component unmounts mid-fetch -> `cancelled` flag
  // (b) user starts typing/sending while fetch is in flight -> userInteractedRef
  // (c) rehydrate completes after a new turn has begun -> only setTurns when
  //     prev list is empty, so we never clobber an in-flight pending turn.
  const loadConversation = useCallback(async (id: string) => {
    try {
      const detail = await fetchConversation(id);
      if (userInteractedRef.current) return;
      const restored = turnsFromMessages(detail.messages);
      if (DEBUG) console.debug("[chat] restored turns", restored.length, "from", id);
      setTurns((prev) => (prev.length === 0 ? restored : prev));
    } catch (e) {
      if (DEBUG) console.warn("[chat] restore failed", e);
      // Stale or deleted conversation; reset so the next send creates a
      // fresh thread instead of stamping onto a server-side ghost.
      conversationIdRef.current = null;
      setConversationId(null);
      storeConversationId(null);
    }
  }, []);

  useEffect(() => {
    const id = conversationIdRef.current;
    if (!id || restoredRef.current) return;
    restoredRef.current = true;
    void loadConversation(id);
  }, [loadConversation]);

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
    restoredRef.current = true;
    userInteractedRef.current = false; // allow rehydrate again if user picks an old conversation
  }, []);

  const switchConversation = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      abortRef.current = null;
      conversationIdRef.current = id;
      setConversationId(id);
      storeConversationId(id);
      setTurns([]); // wipe before reload so old turns don't briefly show
      restoredRef.current = true;
      userInteractedRef.current = false;
      await loadConversation(id);
    },
    [loadConversation],
  );

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
        thinking: "",
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
              if (DEBUG) console.debug("[chat] new conversation_id", cid);
              conversationIdRef.current = cid;
              setConversationId(cid);
              storeConversationId(cid);
            }
          }
          setTurns((prev) => {
            const idx = prev.findIndex((t) => t.id === pendingId);
            if (idx === -1) {
              const recovered: ChatTurn = applyEvent(
                {
                  id: pendingId,
                  role: "assistant",
                  content: "",
                  thinking: "",
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
          if (DEBUG) console.error("[chat] stream error", e);
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
        // Refresh the sidebar so a brand-new conversation appears immediately
        // and existing rows pick up the new last_message_at.
        qc.invalidateQueries({ queryKey: ["conversations"] });
      }
    },
    [busy, turns, qc],
  );

  return { turns, busy, send, stop, newChat, switchConversation, conversationId };
}

function applyEvent(turn: ChatTurn, type: string, data: SseEventData): ChatTurn {
  switch (type) {
    case "text_delta": {
      const text = String(data?.text ?? "");
      return { ...turn, content: turn.content + text };
    }
    case "thinking_delta": {
      const text = String(data?.text ?? "");
      return { ...turn, thinking: (turn.thinking ?? "") + text };
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
      return {
        ...turn,
        pending: false,
        error: true,
        content: turn.content || `Error: ${message}`,
      };
    }
    case "start":
    case "usage":
    default:
      return turn;
  }
}
