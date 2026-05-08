import { Link } from "@tanstack/react-router";
import {
  AlertCircle,
  BookText,
  Calendar,
  CheckCircle2,
  ChevronDown,
  FileText,
  Hammer,
  HelpCircle,
  ListChecks,
  Loader2,
  MapPin,
  Search,
  UserPlus,
  Users,
} from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import { STATUS_PILL } from "@/lib/status-styles";
import { cn } from "@/lib/utils";

import type { ToolCall } from "./ChatStreamProvider";

type SearchHit = {
  chunk_id?: string;
  document_id?: string;
  document_filename?: string | null;
  document_kind?: string | null;
  page?: number | null;
  content?: string;
  score?: number;
};

const SEARCH_TOOLS = new Set(["hybrid_search", "vector_search"]);

function citationsFrom(call: ToolCall): SearchHit[] {
  if (call.status !== "ok") return [];
  if (!SEARCH_TOOLS.has(call.name)) return [];
  const out = (call.output ?? null) as { results?: SearchHit[] } | null;
  return Array.isArray(out?.results) ? out.results : [];
}

const STATUS_LABEL: Record<ToolCall["status"], string> = {
  running: "running",
  ok: "ok",
  error: "error",
};

function StatusIcon({ status }: { status: ToolCall["status"] }) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin" />;
  if (status === "ok") return <CheckCircle2 className="h-3 w-3" />;
  return <AlertCircle className="h-3 w-3" />;
}

function ToolIcon({ name }: { name: string }) {
  const className = "h-3.5 w-3.5 text-muted-foreground";
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
  const citations = citationsFrom(call);
  return (
    <details className="group rounded-md border border-border bg-muted/60 px-2.5 py-1.5 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 text-foreground marker:hidden">
        <ToolIcon name={call.name} />
        <span className="font-mono">{call.name}</span>
        {preview ? (
          <span className="min-w-0 flex-1 truncate text-muted-foreground" title={preview}>
            {preview}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
            STATUS_PILL[call.status],
          )}
        >
          <StatusIcon status={call.status} />
          {STATUS_LABEL[call.status]}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      {citations.length > 0 ? <Citations hits={citations} /> : null}
      {hasInput ? <Section label="Input" value={call.input} /> : null}
      {hasOutput ? <Section label="Output" value={call.output} /> : null}
    </details>
  );
}

function Citations({ hits }: { hits: SearchHit[] }) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Citations
      </div>
      <div className="flex flex-wrap gap-1">
        {hits.map((h) => {
          const id = h.document_id;
          if (!id) return null;
          const label = h.document_filename ?? id.slice(0, 8);
          const snippet = h.content ?? "";
          const key = `${h.chunk_id ?? id}-${h.page ?? ""}`;
          return (
            <Tooltip
              key={key}
              content={snippet.length > 200 ? `${snippet.slice(0, 200)}...` : snippet}
            >
              <Link
                to="/documents"
                search={{ id, page: h.page ?? undefined }}
                className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/15"
              >
                <FileText className="h-3 w-3" />
                <span className="max-w-[160px] truncate">{label}</span>
                {h.page ? <span className="text-primary/80">p.{h.page}</span> : null}
              </Link>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

function Section({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <pre className="overflow-x-auto rounded border border-border bg-card p-2 text-[11px] leading-snug text-foreground">
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
