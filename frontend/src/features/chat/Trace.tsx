/**
 * Trace renderers shared between the main chat bubble and the
 * `traverse_and_summarize` tool card. The trace is a flat list of thinking
 * summaries and tool calls in the order they happened. The shared `<Trace>`
 * wrapper keeps a stable JSX shape across the streaming-to-done transition so
 * React preserves every child's open/closed state; an earlier version
 * remounted the children when the parent JSX flipped between a flat list and
 * a collapsed wrapper, which made the thinking content look like it
 * vanished the moment the turn ended.
 */

import { Brain, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

import { traceSummary, type ThinkingEntry, type TraceEntry } from "./ChatStreamProvider";
import { ToolCallCard } from "./ToolCallCard";

// Strip the inline markdown markers that show up in OpenAI's auto-summarized
// reasoning (e.g. "**Considering ...**, looking for..."). The expanded body
// of a thinking block renders through ReactMarkdown, but the one-line
// preview in the <details> header is a plain <span>, so without this the
// asterisks read literally. A preview is meant for a quick glance, so plain
// text is the right shape; we don't need full markdown rendering.
export function stripInlineMarkdown(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*#+\s+/, "")
    .replace(/^\s*[-*+]\s+/, "")
    .trim();
}

export function Trace({ trace, live }: { trace: TraceEntry[]; live: boolean }) {
  // A single <details> wrapper spans the streaming-to-done transition. React
  // keeps every ThinkingBlock and ToolCallCard mounted across that boundary,
  // so their open state survives instead of remounting closed. Auto-collapse
  // runs exactly once on the live-to-done edge so old bubbles stay compact;
  // it does not fight a user who manually re-opens the wrapper afterward.
  const [open, setOpen] = useState(live);
  const prevLiveRef = useRef(live);
  useEffect(() => {
    if (prevLiveRef.current && !live) setOpen(false);
    prevLiveRef.current = live;
  }, [live]);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="group mb-2 rounded-md border border-border bg-muted/60 text-xs"
    >
      <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-muted-foreground marker:hidden">
        <Brain className={cn("h-3 w-3 text-amber-500", live ? "animate-pulse" : "")} />
        <span className="font-medium">{live ? "Working..." : traceSummary(trace)}</span>
        <ChevronDown className="ml-auto h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-1 border-t border-border p-2">
        <TraceEntries entries={trace} live={live} />
      </div>
    </details>
  );
}

export function TraceEntries({ entries, live }: { entries: TraceEntry[]; live: boolean }) {
  return (
    <>
      {entries.map((entry) =>
        entry.kind === "thinking" ? (
          <ThinkingBlock key={entry.id} entry={entry} live={live} />
        ) : (
          <ToolCallCard key={entry.id} call={entry} />
        ),
      )}
    </>
  );
}

function ThinkingBlock({ entry, live }: { entry: ThinkingEntry; live: boolean }) {
  // Default closed so the user sees a one-line streaming preview (firstLine)
  // rather than a wall of reasoning text. They can click any block open to
  // read the full summary; the parent <Trace> wrapper keeps that state
  // intact when the turn finishes.
  const [open, setOpen] = useState(false);
  const firstLine = entry.text.split(/\n+/).find((line) => line.trim().length > 0) ?? "";
  const preview = stripInlineMarkdown(firstLine);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="group rounded-md border border-amber-200 bg-amber-50 text-xs dark:border-amber-900 dark:bg-amber-950/40"
    >
      <summary
        className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-amber-900 marker:hidden dark:text-amber-200"
        title="Reasoning summary while the model deliberates."
      >
        <Brain
          className={cn(
            "h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400",
            live ? "animate-pulse" : "",
          )}
        />
        <span className="font-medium">Thinking</span>
        {preview ? (
          <span className="min-w-0 flex-1 truncate text-amber-800/70 dark:text-amber-200/60">
            {preview}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-amber-600 transition-transform group-open:rotate-180 dark:text-amber-400" />
      </summary>
      <div className="border-t border-amber-200 px-2.5 py-2 text-amber-900 dark:border-amber-900 dark:text-amber-200">
        {entry.text ? (
          <Markdown content={entry.text} />
        ) : (
          <span className="italic opacity-70">Thinking...</span>
        )}
      </div>
    </details>
  );
}
