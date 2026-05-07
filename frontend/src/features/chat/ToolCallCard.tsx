import {
  AlertCircle,
  BookText,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Hammer,
  HelpCircle,
  ListChecks,
  Loader2,
  MapPin,
  Search,
  UserPlus,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";

import type { ToolCall } from "./useChatStream";

const STATUS_LABEL: Record<ToolCall["status"], string> = {
  running: "running",
  ok: "ok",
  error: "error",
};

const STATUS_CLASS: Record<ToolCall["status"], string> = {
  running: "bg-amber-100 text-amber-800",
  ok: "bg-emerald-100 text-emerald-800",
  error: "bg-red-100 text-red-800",
};

function StatusIcon({ status }: { status: ToolCall["status"] }) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin" />;
  if (status === "ok") return <CheckCircle2 className="h-3 w-3" />;
  return <AlertCircle className="h-3 w-3" />;
}

function ToolIcon({ name }: { name: string }) {
  const className = "h-3.5 w-3.5 text-zinc-500";
  if (name.startsWith("person_search") || name.startsWith("place_search")) {
    return <Search className={className} />;
  }
  if (name === "person_propose_create") return <UserPlus className={className} />;
  if (name.startsWith("person_") || name.startsWith("relationship_")) {
    return <Users className={className} />;
  }
  if (name.startsWith("event_")) return <Calendar className={className} />;
  if (name.startsWith("place_")) return <MapPin className={className} />;
  if (name.startsWith("source_")) return <BookText className={className} />;
  if (name.startsWith("claim_")) return <ListChecks className={className} />;
  if (name === "request_user_input") return <HelpCircle className={className} />;
  return <Hammer className={className} />;
}

/**
 * Build a one-line preview to show next to the tool name when the card is
 * collapsed. We pull the most informative single field out of the input so
 * the user knows at a glance what the agent did without expanding.
 */
function previewFor(call: ToolCall): string | null {
  const input = (call.input ?? null) as Record<string, unknown> | null;
  if (!input) return null;
  const get = (k: string) => {
    const v = input[k];
    return typeof v === "string" && v ? v : null;
  };
  switch (call.name) {
    case "person_search":
    case "place_search":
      return get("query");
    case "person_propose_create":
      return get("display_name");
    case "person_propose_update": {
      const target = get("display_name") ?? get("person_id");
      return target ? `update ${target}` : null;
    }
    case "person_propose_merge":
      return get("loser_id") && get("winner_id")
        ? `merge ${get("loser_id")} into ${get("winner_id")}`
        : null;
    case "relationship_propose_create": {
      const t = get("type") ?? "relationship";
      return `add ${t}`;
    }
    case "relationship_propose_delete":
      return "remove relationship";
    case "event_propose_create": {
      const t = get("type") ?? "event";
      const date = get("date_text");
      return date ? `${t} (${date})` : t;
    }
    case "event_propose_update":
      return "update event";
    case "place_propose_create":
      return get("name");
    case "source_propose_create":
      return get("title");
    case "claim_propose_accept":
      return "accept claim";
    case "claim_propose_reject":
      return "reject claim";
    case "request_user_input":
      return get("reason");
    default:
      return null;
  }
}

export function ToolCallCard({ call }: { call: ToolCall }) {
  const hasInput = call.input !== undefined && call.input !== null;
  const hasOutput = call.output !== undefined && call.output !== null;
  const preview = previewFor(call);
  return (
    <details className="group rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 text-zinc-700 marker:hidden">
        <ToolIcon name={call.name} />
        <span className="font-mono">{call.name}</span>
        {preview ? (
          <span className="min-w-0 flex-1 truncate text-zinc-500" title={preview}>
            {preview}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
            STATUS_CLASS[call.status],
          )}
        >
          <StatusIcon status={call.status} />
          {STATUS_LABEL[call.status]}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-400 transition-transform group-open:rotate-180" />
      </summary>
      {hasInput ? <Section label="Input" value={call.input} /> : null}
      {hasOutput ? <Section label="Output" value={call.output} /> : null}
    </details>
  );
}

function Section({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <pre className="overflow-x-auto rounded bg-white p-2 text-[11px] leading-snug text-zinc-800">
        {format(value)}
      </pre>
    </div>
  );
}

function format(v: unknown): string {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
