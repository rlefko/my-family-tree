import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { apiFetch } from "@/api/client";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
};

type ChatResponse = {
  text: string;
  model: string;
  provider: string;
};

const TREE_ID = "00000000-0000-0000-0000-000000000000";

function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-scroll to the latest message whenever turns change.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // Auto-grow the composer up to a max height.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [prompt]);

  async function send() {
    const trimmed = prompt.trim();
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
    };

    // Snapshot the history we'll send (everything before this user turn).
    const history = turns
      .filter((t) => !t.pending && !t.error)
      .map((t) => ({ role: t.role, content: t.content }));

    setTurns((prev) => [...prev, userTurn, pending]);
    setPrompt("");
    setBusy(true);

    try {
      const res = await apiFetch<ChatResponse>("/api/v1/chat", {
        method: "POST",
        body: JSON.stringify({
          tree_id: TREE_ID,
          message: trimmed,
          history,
        }),
      });
      setTurns((prev) =>
        prev.map((t) => (t.id === pendingId ? { ...t, pending: false, content: res.text } : t)),
      );
    } catch (e) {
      const message = (e as { message?: string }).message ?? String(e);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === pendingId
            ? { ...t, pending: false, error: true, content: `Error: ${message}` }
            : t,
        ),
      );
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter to send, Shift+Enter for newline. Standard chat UX.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <section className="flex h-full flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">Chat</h1>
        <p className="text-xs text-zinc-500">
          Ask about your tree. Multi-turn context is sent on each request.
        </p>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        {turns.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="mx-auto flex max-w-3xl flex-col gap-4">
            {turns.map((turn) => (
              <li
                key={turn.id}
                className={cn(
                  "flex w-full",
                  turn.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                <Bubble turn={turn} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        className="border-t border-zinc-200 bg-white px-4 py-3 sm:px-6"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            ref={inputRef}
            className="flex-1 resize-none rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            placeholder="Ask a question. Shift+Enter for a new line."
            rows={1}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy}
          />
          <button
            type="submit"
            className="inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy || !prompt.trim()}
          >
            {busy ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
}

function Bubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm",
        isUser
          ? "rounded-br-sm bg-indigo-600 text-white"
          : turn.error
            ? "rounded-bl-sm border border-red-200 bg-red-50 text-red-900"
            : "rounded-bl-sm border border-zinc-200 bg-white text-zinc-900",
      )}
    >
      {turn.pending ? (
        <Pending />
      ) : isUser ? (
        <p className="whitespace-pre-wrap break-words">{turn.content}</p>
      ) : (
        <Markdown content={turn.content} />
      )}
    </div>
  );
}

function Pending() {
  return (
    <span className="inline-flex items-center gap-1 text-zinc-400">
      <Dot delay="0ms" />
      <Dot delay="120ms" />
      <Dot delay="240ms" />
    </span>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"
      style={{ animationDelay: delay }}
    />
  );
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 underline-offset-2 hover:underline"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center justify-center py-20 text-center">
      <div className="mb-2 text-4xl">💬</div>
      <h2 className="text-lg font-semibold text-zinc-900">Start a conversation</h2>
      <p className="mt-1 text-sm text-zinc-500">
        Ask the assistant about your tree, a person, a date, or a document. Each turn carries the
        previous context, so you can ask follow-ups.
      </p>
    </div>
  );
}
