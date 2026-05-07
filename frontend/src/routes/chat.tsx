import { createFileRoute } from "@tanstack/react-router";
import { MessageSquarePlus, Send, Square, Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { InlineProposals } from "@/features/chat/InlineProposals";
import { ToolCallCard } from "@/features/chat/ToolCallCard";
import { useChatStream, type ChatTurn } from "@/features/chat/useChatStream";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

function ChatPage() {
  const { turns, busy, send, stop, newChat } = useChatStream();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const draftRef = useRef("");

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    const text = draftRef.current;
    if (!text.trim() || busy) return;
    void send(text);
    draftRef.current = "";
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.style.height = "auto";
    }
  }

  return (
    <section className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Chat</h1>
          <p className="text-xs text-zinc-500">
            Ask about your tree. The assistant queues changes as proposals you can approve right
            here in chat.
          </p>
        </div>
        <button
          type="button"
          onClick={newChat}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm hover:bg-zinc-50"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          New chat
        </button>
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
          submit();
        }}
      >
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            ref={inputRef}
            className="flex-1 resize-none rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Ask a question. Shift+Enter for a new line."
            rows={1}
            onChange={(e) => {
              draftRef.current = e.target.value;
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            }}
            onKeyDown={onKeyDown}
          />
          {busy ? (
            <button
              type="button"
              onClick={stop}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50"
            >
              <Square className="h-3.5 w-3.5" />
              Stop
            </button>
          ) : (
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-3.5 w-3.5" />
              Send
            </button>
          )}
        </div>
      </form>
    </section>
  );
}

function Bubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  const toolCalls = turn.toolCalls ?? [];
  const proposalIds = turn.proposalIds ?? [];
  const hasContent = turn.content && turn.content.length > 0;
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
      {toolCalls.length > 0 ? (
        <div className="mb-2 flex flex-col gap-1">
          {toolCalls.map((call) => (
            <ToolCallCard key={call.id} call={call} />
          ))}
        </div>
      ) : null}
      {hasContent ? (
        isUser ? (
          <p className="whitespace-pre-wrap break-words">{turn.content}</p>
        ) : (
          <Markdown content={turn.content} />
        )
      ) : turn.pending && toolCalls.length === 0 ? (
        <Pending />
      ) : null}
      {!isUser && proposalIds.length > 0 ? <InlineProposals ids={proposalIds} /> : null}
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
      <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
        <Sparkles className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-zinc-900">Start a conversation</h2>
      <p className="mt-1 text-sm text-zinc-500">
        Ask the assistant about your tree, give it new records to file, or have it search for
        what's already there. New records get queued as proposals you can approve right in this
        chat.
      </p>
    </div>
  );
}
