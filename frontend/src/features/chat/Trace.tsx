/**
 * Trace renderers shared between the main chat bubble and the
 * `traverse_and_summarize` tool card. While the agent is working we render
 * each step inline so the user can watch the firstLine previews and tool
 * status pills tick by; once the turn ends we collapse the whole trace
 * behind a one-line summary so old bubbles stay compact.
 */

import { Brain, ChevronDown } from "lucide-react";
import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

import { traceSummary, type ThinkingEntry, type TraceEntry } from "./ChatStreamProvider";
import { ToolCallCard } from "./ToolCallCard";

// Strip inline markdown markers from the one-line preview in the `<details>`
// header. The expanded body renders through ReactMarkdown; the preview is a
// plain `<span>`, so without this OpenAI's `**Considering ...**` summaries
// render literal asterisks.
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
  if (live) {
    // Inline list with no outer wrapper so the user does not have to click
    // through an extra collapsible layer to see what the agent is doing
    // right now. Each thinking block and tool card stays individually
    // collapsible.
    return (
      <div className="mb-2 flex flex-col gap-1">
        <TraceEntries entries={trace} live />
      </div>
    );
  }
  return <CollapsedTrace trace={trace} />;
}

function CollapsedTrace({ trace }: { trace: TraceEntry[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="mb-2 rounded-md border border-border bg-muted/60 text-xs"
    >
      <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-muted-foreground marker:hidden">
        <Brain className="h-3 w-3 text-amber-500" />
        <span className="font-medium">{traceSummary(trace)}</span>
        <ChevronDown
          className={cn("ml-auto h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </summary>
      <div className="flex flex-col gap-1 border-t border-border p-2">
        <TraceEntries entries={trace} live={false} />
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
  // Default closed so the streaming summary is a one-line preview rather
  // than a wall of reasoning text. The user can click any block open to
  // read the full summary.
  const [open, setOpen] = useState(false);
  const firstLine = entry.text.split(/\n+/).find((line) => line.trim().length > 0) ?? "";
  const preview = stripInlineMarkdown(firstLine);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="rounded-md border border-amber-200 bg-amber-50 text-xs dark:border-amber-900 dark:bg-amber-950/40"
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
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-amber-600 transition-transform dark:text-amber-400",
            open && "rotate-180",
          )}
        />
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
