/**
 * Inline proposal review surface that lives at the bottom of an assistant
 * bubble. Shows each queued proposal as a one-line summary with Approve and
 * Reject buttons; offers an Approve all shortcut and a link to the full
 * Proposals page for diffing complex payloads.
 *
 * Uses the same `useApproveProposal` / `useRejectProposal` / `useApproveBatch`
 * hooks as the dedicated `/proposals` page so optimistic state stays in
 * sync, so approving here updates the badge here AND any open proposals tab.
 */

import { Link } from "@tanstack/react-router";
import {
  Calendar,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Layers,
  MapPin,
  UserPlus,
  Users,
  X,
  XCircle,
} from "lucide-react";
import { useMemo } from "react";

import {
  useApproveBatch,
  useApproveProposal,
  useProposals,
  useRejectProposal,
  type ProposalRow,
} from "@/api/endpoints/proposals";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const ACTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  "create:person": UserPlus,
  "update:person": Users,
  "merge:person": Users,
  "create:relationship": Users,
  "delete:relationship": XCircle,
  "create:event": Calendar,
  "update:event": Calendar,
  "create:place": MapPin,
  "create:source": Layers,
  "create:document": Layers,
};

function iconFor(p: ProposalRow) {
  const key = `${p.action}:${p.target_type ?? ""}`;
  return ACTION_ICONS[key] ?? Layers;
}

function summaryFor(p: ProposalRow): string {
  const payload = p.payload || {};
  const display = (payload.display_name as string) || (payload.name as string);
  const action = labelFor(p);
  if (display) return `${action}: ${display}`;
  if (p.target_type === "relationship") {
    const t = (payload.type as string) || "rel";
    return `${action} (${t})`;
  }
  if (p.target_type === "event") {
    const t = (payload.type as string) || "event";
    const date = (payload.date_text as string) || "";
    return `${action}: ${t}${date ? ` ${date}` : ""}`;
  }
  return action;
}

function labelFor(p: ProposalRow): string {
  const t = p.target_type ?? "item";
  const a = p.action;
  if (a === "create") return `Add ${t}`;
  if (a === "update") return `Update ${t}`;
  if (a === "merge") return `Merge ${t}`;
  if (a === "delete") return `Delete ${t}`;
  if (a === "accept_claim") return "Accept claim";
  if (a === "reject_claim") return "Reject claim";
  if (a === "resolve_conflict") return "Resolve conflict";
  return `${a} ${t}`;
}

export function InlineProposals({ ids }: { ids: string[] }) {
  // `null` = no status filter, returns proposals across every status so an
  // approved/rejected row stays visible (with its badge) instead of falling
  // out of the fetch and triggering a "loading..." flash.
  const { data, isLoading } = useProposals(null);
  const approveMutation = useApproveProposal();
  const rejectMutation = useRejectProposal();
  const approveBatch = useApproveBatch();

  const matched = useMemo(() => {
    if (!data) return [] as ProposalRow[];
    const byId = new Map<string, ProposalRow>(data.items.map((p) => [p.id, p]));
    return ids.map((id) => byId.get(id)).filter((p): p is ProposalRow => Boolean(p));
  }, [data, ids]);

  if (ids.length === 0) return null;
  if (isLoading && matched.length === 0) {
    return (
      <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-700">
        Loading {ids.length} queued proposal{ids.length === 1 ? "" : "s"}...
      </div>
    );
  }
  if (matched.length === 0) {
    // Loaded but the proposals are gone (deleted out-of-band). Stay quiet.
    return null;
  }

  const pending = matched.filter((p) => p.status === "pending");
  const allResolved = pending.length === 0;
  const approvedCount = matched.filter((p) => p.status === "approved").length;
  const rejectedCount = matched.filter((p) => p.status === "rejected").length;

  // Once every proposal in this set is resolved, collapse the whole block
  // into a single summary line; click to expand the audit trail.
  if (allResolved) {
    const parts: string[] = [];
    if (approvedCount) parts.push(`${approvedCount} approved`);
    if (rejectedCount) parts.push(`${rejectedCount} rejected`);
    const summary = parts.join(" · ") || "all resolved";
    return (
      <details className="group mt-3 rounded-md border border-emerald-100 bg-emerald-50/40 text-xs">
        <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-emerald-900 marker:hidden">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          <span className="font-medium">
            {matched.length} proposal{matched.length === 1 ? "" : "s"} ({summary})
          </span>
          <ChevronDown className="ml-auto h-3.5 w-3.5 text-emerald-600 transition-transform group-open:rotate-180" />
        </summary>
        <ul className="space-y-1 border-t border-emerald-100 p-2">
          {matched.map((p) => (
            <ProposalLineItem
              key={p.id}
              p={p}
              onApprove={() => approveMutation.mutate(p.id)}
              onReject={() => rejectMutation.mutate(p.id)}
              busy={false}
            />
          ))}
        </ul>
      </details>
    );
  }

  return (
    <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/40 p-2">
      <div className="flex items-center justify-between gap-2 px-1.5 pb-1.5">
        <span className="text-xs font-medium text-indigo-900">
          {matched.length} proposal{matched.length === 1 ? "" : "s"} ({pending.length} pending)
        </span>
        <div className="flex items-center gap-2">
          {pending.length > 1 ? (
            <button
              type="button"
              onClick={() => approveBatch.mutate(pending.map((p) => p.id))}
              disabled={approveBatch.isPending}
              className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-[11px] font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              <CheckCheck className="h-3 w-3" />
              Approve all
            </button>
          ) : null}
          <Link
            to="/proposals"
            search={{ ids: ids.join(",") }}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-700 hover:text-indigo-900"
          >
            <ExternalLink className="h-3 w-3" />
            Open
          </Link>
        </div>
      </div>
      <ul className="space-y-1">
        {matched.map((p) => (
          <ProposalLineItem
            key={p.id}
            p={p}
            onApprove={() => approveMutation.mutate(p.id)}
            onReject={() => rejectMutation.mutate(p.id)}
            busy={approveMutation.isPending || rejectMutation.isPending || approveBatch.isPending}
          />
        ))}
      </ul>
    </div>
  );
}

function ProposalLineItem({
  p,
  onApprove,
  onReject,
  busy,
}: {
  p: ProposalRow;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  const Icon = iconFor(p);
  const isPending = p.status === "pending";
  const statusClasses: Record<string, string> = {
    pending: "bg-white border border-zinc-200 text-zinc-700",
    approved: "bg-emerald-50 border border-emerald-200 text-emerald-800",
    rejected: "bg-zinc-100 border border-zinc-200 text-zinc-500 line-through",
    expired: "bg-zinc-100 border border-zinc-200 text-zinc-500",
  };
  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs",
        statusClasses[p.status] ?? statusClasses.pending,
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-indigo-700" />
      <span className="flex-1 truncate" title={p.rationale ?? undefined}>
        {summaryFor(p)}
      </span>
      {p.status === "approved" || p.confidence >= 100 ? null : (
        <Tooltip
          content={`Confidence in this proposal: ${p.confidence}/100. 100 means a direct user assertion; lower scores reflect inferences the agent made.`}
        >
          <span className="shrink-0 cursor-help text-[10px] uppercase tracking-wide text-zinc-400">
            {p.confidence}%
          </span>
        </Tooltip>
      )}
      {isPending ? (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-60"
            aria-label="Approve proposal"
          >
            <Check className="h-3 w-3" />
            Approve
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded border border-zinc-300 bg-white px-2 py-0.5 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
            aria-label="Reject proposal"
          >
            <X className="h-3 w-3" />
            Reject
          </button>
        </div>
      ) : (
        <span className="shrink-0 text-[11px] font-medium capitalize">{p.status}</span>
      )}
    </li>
  );
}
