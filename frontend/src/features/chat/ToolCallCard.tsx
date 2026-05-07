import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Hammer,
  Loader2,
  Search,
  UserPlus,
  Users,
  Calendar,
  MapPin,
  BookText,
  ListChecks,
  HelpCircle,
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

export function ToolCallCard({
  call,
  turnDone,
}: {
  call: ToolCall;
  turnDone?: boolean;
}) {
  const hasInput = call.input !== undefined && call.input !== null;
  const hasOutput = call.output !== undefined && call.output !== null;
  // Open while the turn is still streaming or this specific call is running,
  // so the user sees what's happening live. Once the turn is done, collapse
  // by default — user can click the chevron to expand and inspect.
  const initiallyOpen = !turnDone || call.status === "running";
  return (
    <details
      key={`${call.id}:${turnDone ? "done" : "live"}`}
      open={initiallyOpen}
      className="group rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs"
    >
      <summary className="flex cursor-pointer items-center gap-2 text-zinc-700 marker:hidden">
        <ToolIcon name={call.name} />
        <span className="font-mono">{call.name}</span>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
            STATUS_CLASS[call.status],
          )}
        >
          <StatusIcon status={call.status} />
          {STATUS_LABEL[call.status]}
        </span>
        <ChevronDown className="ml-auto h-3.5 w-3.5 text-zinc-400 transition-transform group-open:rotate-180" />
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
