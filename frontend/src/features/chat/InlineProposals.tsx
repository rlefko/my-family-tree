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
import { PROPOSAL_ROW_TONE } from "@/lib/status-styles";
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
      <div className="mt-3 rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-primary">
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
      <details className="group mt-3 rounded-md border border-emerald-200 bg-emerald-50/40 text-xs dark:border-emerald-900 dark:bg-emerald-950/30">
        <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-emerald-900 marker:hidden dark:text-emerald-200">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
          <span className="font-medium">
            {matched.length} proposal{matched.length === 1 ? "" : "s"} ({summary})
          </span>
          <ChevronDown className="ml-auto h-3.5 w-3.5 text-emerald-600 transition-transform group-open:rotate-180 dark:text-emerald-400" />
        </summary>
        <ul className="space-y-1 border-t border-emerald-200 p-2 dark:border-emerald-900">
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
    <div className="mt-3 rounded-md border border-primary/20 bg-primary/5 p-2">
      <div className="flex items-center justify-between gap-2 px-1.5 pb-1.5">
        <span className="text-xs font-medium text-primary">
          {matched.length} proposal{matched.length === 1 ? "" : "s"} ({pending.length} pending)
        </span>
        <div className="flex items-center gap-2">
          {pending.length > 1 ? (
            <button
              type="button"
              onClick={() => approveBatch.mutate(pending.map((p) => p.id))}
              disabled={approveBatch.isPending}
              className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-60"
            >
              <CheckCheck className="h-3 w-3" />
              Approve all
            </button>
          ) : null}
          <Link
            to="/proposals"
            search={{ ids: ids.join(",") }}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:text-primary/80"
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
  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs",
        PROPOSAL_ROW_TONE[p.status] ?? PROPOSAL_ROW_TONE.pending,
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
      <span className="flex-1 truncate" title={p.rationale ?? undefined}>
        {summaryFor(p)}
      </span>
      {p.status === "approved" || p.confidence >= 100 ? null : (
        <Tooltip
          content={`Confidence in this proposal: ${p.confidence}/100. 100 means a direct user assertion; lower scores reflect inferences the agent made.`}
        >
          <span className="shrink-0 cursor-help text-[10px] uppercase tracking-wide text-muted-foreground">
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
            className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-60 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
            aria-label="Approve proposal"
          >
            <Check className="h-3 w-3" />
            Approve
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded border border-input bg-background px-2 py-0.5 text-[11px] font-medium text-foreground hover:bg-muted disabled:opacity-60"
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
