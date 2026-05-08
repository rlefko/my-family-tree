/**
 * Trace renderers shared between the main chat bubble and the
 * `traverse_and_summarize` tool card. The trace is a flat list of thinking
 * summaries and tool calls in the order they happened; live runs render the
 * trace inline (default open while streaming) while finished runs collapse it
 * behind a one-line summary.
 */

import { Brain, ChevronDown } from "lucide-react";
import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

import { traceSummary, type ThinkingEntry, type TraceEntry } from "./ChatStreamProvider";
import { ToolCallCard } from "./ToolCallCard";

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

export function CollapsedTrace({ trace }: { trace: TraceEntry[] }) {
  // Switching the parent JSX shape (flat list -> this wrapper) remounts every
  // inner ThinkingBlock and ToolCallCard, resetting each to its closed default.
  return (
    <details className="group mb-2 rounded-md border border-border bg-muted/60 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-muted-foreground marker:hidden">
        <Brain className="h-3 w-3 text-amber-500" />
        <span className="font-medium">{traceSummary(trace)}</span>
        <ChevronDown className="ml-auto h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-1 border-t border-border p-2">
        <TraceEntries entries={trace} live={false} />
      </div>
    </details>
  );
}

export function ThinkingBlock({ entry, live }: { entry: ThinkingEntry; live: boolean }) {
  // Default open while streaming so the user can read along, closed once the
  // turn ends so old bubbles stay compact. The user's toggle is preserved
  // across re-renders.
  const [open, setOpen] = useState(live);
  const firstLine = entry.text.split(/\n+/).find((line) => line.trim().length > 0) ?? "";
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
        {firstLine ? (
          <span className="min-w-0 flex-1 truncate text-amber-800/70 dark:text-amber-200/60">
            {firstLine}
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
