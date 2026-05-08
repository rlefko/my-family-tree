import { createFileRoute } from "@tanstack/react-router";
import {
  HelpCircle,
  Loader2,
  MessageSquarePlus,
  Paperclip,
  Send,
  Sparkles,
  Square,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useConversations } from "@/api/endpoints/conversations";
import { documentRawUrl, uploadDocumentRequest } from "@/api/endpoints/documents";
import { Markdown } from "@/components/Markdown";
import { ChatAttachments, type ChatAttachment } from "@/features/chat/ChatAttachments";
import { InlineProposals } from "@/features/chat/InlineProposals";
import { CollapsedTrace, TraceEntries } from "@/features/chat/Trace";
import {
  useChatStream,
  type ChatAttachmentRef,
  type ChatTurn,
  type NeedsInputPrompt,
  type ToolEntry,
} from "@/features/chat/ChatStreamProvider";
import { MAX_UPLOAD_BYTES, formatBytes } from "@/features/documents/constants";
import { DEFAULT_TREE_ID } from "@/lib/tree";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

function ChatPage() {
  const { turns, busy, send, stop, newChat, switchConversation, conversationId, markSeen } =
    useChatStream();
  const conversations = useConversations();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const draftRef = useRef("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const uploading = attachments.some((a) => a.status === "uploading");

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // Clear the "new chat result" badge as soon as the user lands here.
  useEffect(() => {
    markSeen();
  }, [markSeen, turns]);

  const enqueueFiles = useCallback((files: File[]) => {
    for (const file of files) {
      const tempId = crypto.randomUUID();
      if (file.size > MAX_UPLOAD_BYTES) {
        setAttachments((prev) => [
          ...prev,
          {
            tempId,
            filename: file.name,
            status: "failed",
            progress: 0,
            error: `File too large (max ${formatBytes(MAX_UPLOAD_BYTES)})`,
          },
        ]);
        continue;
      }
      setAttachments((prev) => [
        ...prev,
        { tempId, filename: file.name, status: "uploading", progress: 0 },
      ]);
      uploadDocumentRequest({
        file,
        treeId: DEFAULT_TREE_ID,
        onProgress: (loaded, total) => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.tempId === tempId ? { ...a, progress: total > 0 ? loaded / total : 0 } : a,
            ),
          );
        },
      })
        .then((doc) => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.tempId === tempId
                ? {
                    ...a,
                    status: "ready",
                    progress: 1,
                    documentId: doc.document_id,
                    mimeType: doc.mime_type,
                    kind: doc.kind,
                  }
                : a,
            ),
          );
        })
        .catch((err: { message?: string }) => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.tempId === tempId
                ? { ...a, status: "failed", error: err.message ?? "upload failed" }
                : a,
            ),
          );
        });
    }
  }, []);

  function removeAttachment(tempId: string) {
    setAttachments((prev) => prev.filter((a) => a.tempId !== tempId));
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    const text = draftRef.current;
    if (!text.trim() || busy || uploading) return;
    const ready = attachments.flatMap((a) =>
      a.status === "ready" && a.documentId
        ? [
            {
              documentId: a.documentId,
              filename: a.filename,
              mimeType: a.mimeType,
              kind: a.kind,
            },
          ]
        : [],
    );
    void send(text, ready);
    draftRef.current = "";
    setAttachments([]);
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.style.height = "auto";
    }
  }

  return (
    <section className="flex h-full">
      <ConversationSidebar
        conversations={conversations.data?.items ?? []}
        loading={conversations.isLoading}
        activeId={conversationId}
        onSelect={(id) => void switchConversation(id)}
        onNewChat={newChat}
      />

      <div className="relative flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-card px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold text-foreground">Chat</h1>
            <p className="text-xs text-muted-foreground">
              Ask about your tree. The assistant queues changes as proposals you can approve right
              here in chat.
            </p>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto bg-muted/40 px-4 py-6 sm:px-6">
          {turns.length === 0 ? (
            <EmptyState />
          ) : (
            <ul className="mx-auto flex max-w-3xl flex-col gap-4">
              <ChatTurns turns={turns} />
            </ul>
          )}
        </div>

        <form
          className="border-t border-border bg-card px-4 py-3 sm:px-6"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <ChatAttachments items={attachments} onRemove={removeAttachment} />
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                if (files.length > 0) enqueueFiles(files);
                e.currentTarget.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach files"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-input bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Paperclip className="h-3.5 w-3.5" />
            </button>
            <textarea
              ref={inputRef}
              className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
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
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted"
              >
                <Square className="h-3.5 w-3.5" />
                Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={uploading}
                className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" />
                Send
              </button>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}

function ConversationSidebar({
  conversations,
  loading,
  activeId,
  onSelect,
  onNewChat,
}: {
  conversations: { id: string; title: string | null; last_message_at: string | null }[];
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card">
      <div className="border-b border-border px-3 py-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/15"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          New chat
        </button>
      </div>
      <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Recent
      </div>
      <div className="flex-1 overflow-y-auto px-1 pb-3">
        {loading ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">Loading...</div>
        ) : conversations.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">No conversations yet.</div>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  className={cn(
                    "block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-muted",
                    c.id === activeId
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  title={c.title ?? "(untitled)"}
                >
                  <div className="truncate font-medium">{c.title ?? "(untitled)"}</div>
                  {c.last_message_at ? (
                    <div className="truncate text-[10px] text-muted-foreground/70">
                      {new Date(c.last_message_at).toLocaleString()}
                    </div>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

function ChatTurns({ turns }: { turns: ChatTurn[] }) {
  // Compute the index of the most recent assistant turn once so the prompt
  // card only renders on it, not on stale earlier turns whose questions were
  // already answered.
  let latestAssistantIndex = -1;
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].role === "assistant") {
      latestAssistantIndex = i;
      break;
    }
  }
  return (
    <>
      {turns.map((turn, idx) => (
        <li
          key={turn.id}
          className={cn(
            "flex w-full",
            turn.role === "user" ? "justify-end" : "justify-start",
          )}
        >
          <Bubble turn={turn} isLatestAssistant={idx === latestAssistantIndex} />
        </li>
      ))}
    </>
  );
}

function Bubble({ turn, isLatestAssistant }: { turn: ChatTurn; isLatestAssistant: boolean }) {
  const isUser = turn.role === "user";
  const trace = turn.trace ?? [];
  const proposalIds = turn.proposalIds ?? [];
  const attachments = turn.attachments ?? [];
  const hasContent = !!turn.content;
  const hasTrace = trace.length > 0;
  const isQuiet = !hasContent && !hasTrace && attachments.length === 0;
  const runningTool = trace.find(
    (e): e is ToolEntry => e.kind === "tool" && e.status === "running",
  );
  const live = Boolean(turn.pending);
  const showPrompt = !isUser && isLatestAssistant && Boolean(turn.needsInput) && !turn.pending;
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm",
        isUser
          ? "rounded-br-sm bg-primary text-primary-foreground"
          : turn.error
            ? "rounded-bl-sm border border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
            : "rounded-bl-sm border border-border bg-card text-card-foreground",
      )}
    >
      {!isUser && hasTrace ? (
        live ? (
          <div className="mb-2 flex flex-col gap-1">
            <TraceEntries entries={trace} live />
          </div>
        ) : (
          <CollapsedTrace trace={trace} />
        )
      ) : null}
      {isUser && attachments.length > 0 ? <UserAttachments items={attachments} /> : null}
      {hasContent ? (
        isUser ? (
          <p className="whitespace-pre-wrap break-words">{turn.content}</p>
        ) : (
          <Markdown content={turn.content} />
        )
      ) : turn.pending && isQuiet ? (
        <PendingHero />
      ) : !isUser && isQuiet && !turn.pending ? (
        <span className="text-xs italic text-muted-foreground">(no response, try rephrasing)</span>
      ) : null}
      {!isUser && turn.pending && !isQuiet ? (
        <BusyFooter runningToolName={runningTool?.name ?? null} isStreamingText={hasContent} />
      ) : null}
      {showPrompt && turn.needsInput ? <UserInputPrompt prompt={turn.needsInput} /> : null}
      {!isUser && proposalIds.length > 0 ? <InlineProposals ids={proposalIds} /> : null}
    </div>
  );
}

function UserInputPrompt({ prompt }: { prompt: NeedsInputPrompt }) {
  const { send, busy } = useChatStream();
  const options = prompt.options ?? [];
  const submit = (text: string) => {
    if (busy || !text.trim()) return;
    void send(text);
  };
  return (
    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/70 p-2.5 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
        <HelpCircle className="h-3 w-3" />
        Question for you
      </div>
      <Markdown content={prompt.question} />
      {options.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => submit(opt)}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100/80 px-2 py-1 text-xs font-medium text-amber-900 hover:bg-amber-200 disabled:opacity-60 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
            >
              {opt}
            </button>
          ))}
          <button
            type="button"
            onClick={() => submit("(no answer)")}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-md border border-input bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-60"
          >
            Skip
          </button>
        </div>
      ) : (
        <div className="mt-2 text-[11px] text-amber-800/80 dark:text-amber-200/80">
          Type your reply in the chat box below.
        </div>
      )}
    </div>
  );
}

function UserAttachments({ items }: { items: ChatAttachmentRef[] }) {
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {items.map((a) => {
        const isImage = (a.mimeType ?? "").startsWith("image/") || a.kind === "image";
        const rawUrl = documentRawUrl(a.documentId);
        if (isImage) {
          return (
            <a
              key={a.documentId}
              href={rawUrl}
              target="_blank"
              rel="noreferrer"
              className="block overflow-hidden rounded-md border border-primary-foreground/30 bg-primary-foreground/10"
              title={a.filename}
            >
              <img
                src={rawUrl}
                alt={a.filename}
                className="block max-h-48 max-w-full object-contain"
              />
            </a>
          );
        }
        return (
          <a
            key={a.documentId}
            href={rawUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 py-1 text-xs"
            title={a.filename}
          >
            <Paperclip className="h-3 w-3" />
            <span className="max-w-[200px] truncate">{a.filename}</span>
          </a>
        );
      })}
    </div>
  );
}

function BusyFooter({
  runningToolName,
  isStreamingText,
}: {
  runningToolName: string | null;
  isStreamingText: boolean;
}) {
  const label = runningToolName
    ? `Calling ${runningToolName}...`
    : isStreamingText
      ? "Writing reply..."
      : "Working...";
  return (
    <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
      <Loader2 className="h-3 w-3 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function PendingHero() {
  return (
    <span className="inline-flex items-center gap-2 text-muted-foreground">
      <Loader2 className="h-3 w-3 animate-spin text-primary" />
      <span className="text-xs">Thinking...</span>
    </span>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center justify-center py-20 text-center">
      <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Sparkles className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-foreground">Start a conversation</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Ask the assistant about your tree, give it new records to file, or have it search for what's
        already there. New records get queued as proposals you can approve right in this chat.
      </p>
    </div>
  );
}
