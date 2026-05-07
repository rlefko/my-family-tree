/**
 * Inline proposal review surface that lives at the bottom of an assistant
 * bubble. Shows each queued proposal as a one-line summary with Approve and
 * Reject buttons; offers an Approve all shortcut and a link to the full
 * Proposals page for diffing complex payloads.
 *
 * Uses the same `useApproveProposal` / `useRejectProposal` / `useApproveBatch`
 * hooks as the dedicated `/proposals` page so optimistic state stays in
 * sync — approving here updates the badge here AND any open proposals tab.
 */

import { Link } from "@tanstack/react-router";
import {
  Calendar,
  Check,
  CheckCheck,
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
  const { data } = useProposals(null);
  const approveMutation = useApproveProposal();
  const rejectMutation = useRejectProposal();
  const approveBatch = useApproveBatch();

  const matched = useMemo(() => {
    if (!data) return [] as ProposalRow[];
    const set = new Set(ids);
    const byId = new Map<string, ProposalRow>(data.items.map((p) => [p.id, p]));
    return ids.map((id) => byId.get(id)).filter((p): p is ProposalRow => Boolean(p && set.has(p.id)));
  }, [data, ids]);

  if (ids.length === 0) return null;
  if (matched.length === 0) {
    // Proposals fetch hasn't loaded yet; show a lightweight placeholder.
    return (
      <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-xs text-indigo-700">
        Loading {ids.length} queued proposal{ids.length === 1 ? "" : "s"}...
      </div>
    );
  }

  const pending = matched.filter((p) => p.status === "pending");

  return (
    <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/40 p-2">
      <div className="flex items-center justify-between gap-2 px-1.5 pb-1.5">
        <span className="text-xs font-medium text-indigo-900">
          Queued {matched.length} proposal{matched.length === 1 ? "" : "s"}
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
      <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-400">
        {p.confidence}%
      </span>
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
