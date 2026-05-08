/**
 * App-level provider that owns the chat-streaming state. Lives outside the
 * `/chat` route so navigating to other pages does NOT unmount the hook,
 * which previously cancelled the in-flight SSE connection (the AbortController
 * in the unmount cleanup fired and tore down the OpenAI request mid-stream).
 *
 * Components subscribe via `useChatStream()`. The sidebar reads the busy
 * flag and the unseen-result counter to badge the Chat nav link; the chat
 * page reads the full turn list.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useRouterState } from "@tanstack/react-router";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import {
  fetchConversation,
  type AssistantBlock,
  type MessageRow,
  type UserAttachmentBlock,
  type UserBlock,
} from "@/api/endpoints/conversations";
import { postSSE } from "@/api/sse";
import { DEFAULT_TREE_ID } from "@/lib/tree";

const DEBUG = typeof import.meta !== "undefined" && import.meta.env?.DEV;

export type ToolCall = {
  id: string;
  name: string;
  status: "running" | "ok" | "error";
  input?: unknown;
  output?: unknown;
};

export type ThinkingEntry = { kind: "thinking"; id: string; text: string };
export type ToolEntry = { kind: "tool" } & ToolCall;
export type TraceEntry = ThinkingEntry | ToolEntry;

export function traceSummary(trace: TraceEntry[]): string {
  const toolCount = trace.reduce((n, e) => (e.kind === "tool" ? n + 1 : n), 0);
  if (toolCount === 0) return "Reasoning summary";
  return `Reasoned and used ${toolCount} tool${toolCount === 1 ? "" : "s"}`;
}

export type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
  trace?: TraceEntry[];
  proposalIds?: string[];
  attachments?: ChatAttachmentRef[];
};

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
      const blocks = m.content as UserBlock[];
      const text = blocks
        .filter((b): b is Extract<UserBlock, { type: "text" }> => b.type === "text")
        .map((b) => b.text)
        .join("");
      const attachments = blocks
        .filter((b): b is UserAttachmentBlock => b.type === "attachment")
        .map((b) => ({
          documentId: b.document_id,
          filename: b.filename ?? "document",
          mimeType: b.mime_type ?? null,
          kind: b.kind ?? null,
        }));
      turns.push({
        id: m.id,
        role: "user",
        content: text,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
    } else if (m.role === "assistant") {
      const turn: ChatTurn = {
        id: m.id,
        role: "assistant",
        content: "",
        trace: [],
        proposalIds: [],
      };
      for (const block of m.content as AssistantBlock[]) {
        if (block.type === "text") {
          turn.content += block.text;
        } else if (block.type === "tool_use") {
          // Raw thinking is never persisted; rehydrated traces only carry tools.
          turn.trace = [
            ...(turn.trace ?? []),
            {
              kind: "tool",
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

export type ChatAttachmentRef = {
  documentId: string;
  filename: string;
  mimeType?: string | null;
  kind?: string | null;
};

export type ChatStreamValue = {
  turns: ChatTurn[];
  busy: boolean;
  conversationId: string | null;
  unseenCount: number;
  send: (text: string, attachments?: ChatAttachmentRef[]) => Promise<void>;
  stop: () => void;
  newChat: () => void;
  switchConversation: (id: string) => Promise<void>;
  markSeen: () => void;
};

const ChatStreamContext = createContext<ChatStreamValue | null>(null);

export function useChatStream(): ChatStreamValue {
  const ctx = useContext(ChatStreamContext);
  if (ctx === null) {
    throw new Error("useChatStream must be used inside <ChatStreamProvider>");
  }
  return ctx;
}

export function ChatStreamProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const routerState = useRouterState({ select: (s) => s.location.pathname });
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(() =>
    readStoredConversationId(),
  );
  const [unseenCount, setUnseenCount] = useState(0);
  const conversationIdRef = useRef<string | null>(conversationId);
  const abortRef = useRef<AbortController | null>(null);
  const restoredRef = useRef(false);
  const userInteractedRef = useRef(false);
  const onChatPageRef = useRef<boolean>(routerState === "/chat");

  // Track whether the user is currently viewing /chat so we know whether
  // toast/badge notifications are needed when a turn finishes.
  useEffect(() => {
    onChatPageRef.current = routerState === "/chat";
  }, [routerState]);

  const loadConversation = useCallback(async (id: string) => {
    try {
      const detail = await fetchConversation(id);
      if (userInteractedRef.current) return;
      const restored = turnsFromMessages(detail.messages);
      if (DEBUG) console.debug("[chat] restored turns", restored.length, "from", id);
      setTurns((prev) => (prev.length === 0 ? restored : prev));
    } catch (e) {
      if (DEBUG) console.warn("[chat] restore failed", e);
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
    userInteractedRef.current = false;
  }, []);

  const markSeen = useCallback(() => {
    setUnseenCount(0);
  }, []);

  const switchConversation = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      abortRef.current = null;
      conversationIdRef.current = id;
      setConversationId(id);
      storeConversationId(id);
      setTurns([]);
      restoredRef.current = true;
      userInteractedRef.current = false;
      await loadConversation(id);
    },
    [loadConversation],
  );

  const send = useCallback(
    async (text: string, attachments?: ChatAttachmentRef[]) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      userInteractedRef.current = true;

      const ready = (attachments ?? []).filter((a) => a.documentId);
      const wireAttachments = ready.map((a) => ({ document_id: a.documentId }));

      const userTurn: ChatTurn = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        attachments: ready.length > 0 ? ready : undefined,
      };
      const pendingId = crypto.randomUUID();
      const pending: ChatTurn = {
        id: pendingId,
        role: "assistant",
        content: "",
        pending: true,
        trace: [],
        proposalIds: [],
      };

      setTurns((prev) => {
        const history = prev.filter((t) => !t.pending && !t.error);
        return [...history, userTurn, pending];
      });

      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const evt of postSSE<SseEventData>(
          "/api/v1/chat/stream",
          {
            tree_id: DEFAULT_TREE_ID,
            message: trimmed,
            attachments: wireAttachments,
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
                  pending: true,
                  trace: [],
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
        // Defensive: if the stream ended without a `done` event, clear pending.
        let finalized: ChatTurn | undefined;
        setTurns((prev) =>
          prev.map((t) => {
            if (t.id !== pendingId) return t;
            const updated = { ...t, pending: false };
            finalized = updated;
            return updated;
          }),
        );
        qc.invalidateQueries({ queryKey: ["conversations"] });

        // Notify the user if they're not currently looking at /chat.
        if (!onChatPageRef.current && finalized && !finalized.error) {
          setUnseenCount((c) => c + 1);
          const proposalCount = finalized.proposalIds?.length ?? 0;
          const summary = proposalCount
            ? `Chat finished, ${proposalCount} proposal${proposalCount === 1 ? "" : "s"} queued`
            : "Chat finished";
          toast(summary, { description: "Open Chat to review." });
        }
      }
    },
    [busy, qc],
  );

  const value = useMemo<ChatStreamValue>(
    () => ({
      turns,
      busy,
      conversationId,
      unseenCount,
      send,
      stop,
      newChat,
      switchConversation,
      markSeen,
    }),
    [turns, busy, conversationId, unseenCount, send, stop, newChat, switchConversation, markSeen],
  );

  return <ChatStreamContext.Provider value={value}>{children}</ChatStreamContext.Provider>;
}

export function applyEvent(turn: ChatTurn, type: string, data: SseEventData): ChatTurn {
  switch (type) {
    case "text_delta": {
      const text = String(data?.text ?? "");
      return { ...turn, content: turn.content + text };
    }
    case "thinking_delta": {
      const text = String(data?.text ?? "");
      const trace = turn.trace ?? [];
      const last = trace[trace.length - 1];
      if (last?.kind === "thinking") {
        const next = trace.slice(0, -1);
        next.push({ ...last, text: last.text + text });
        return { ...turn, trace: next };
      }
      return {
        ...turn,
        trace: [...trace, { kind: "thinking", id: crypto.randomUUID(), text }],
      };
    }
    case "tool_use_started": {
      const id = String(data?.id ?? "");
      const name = String(data?.name ?? "tool");
      return {
        ...turn,
        trace: [...(turn.trace ?? []), { kind: "tool", id, name, status: "running" }],
      };
    }
    case "tool_use_finished": {
      const id = String(data?.id ?? "");
      return {
        ...turn,
        trace: (turn.trace ?? []).map((e) =>
          e.kind === "tool" && e.id === id ? { ...e, input: data?.input ?? e.input } : e,
        ),
      };
    }
    case "tool_result": {
      const id = String((data as { tool_use_id?: string })?.tool_use_id ?? "");
      const isError = Boolean((data as { is_error?: boolean })?.is_error);
      return {
        ...turn,
        trace: (turn.trace ?? []).map((e) =>
          e.kind === "tool" && e.id === id
            ? {
                ...e,
                status: isError ? "error" : "ok",
                output: (data as { output?: unknown })?.output,
              }
            : e,
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
