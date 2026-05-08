import { useState } from "react";

import {
  useApproveBatch,
  useApproveProposal,
  useProposals,
  useRejectProposal,
  type ProposalRow,
} from "@/api/endpoints/proposals";
import { STATUS_PILL } from "@/lib/status-styles";
import { cn } from "@/lib/utils";

import { ProposalDiff } from "./ProposalDiff";

export function ProposalList({ highlightIds = [] }: { highlightIds?: string[] }) {
  const { data, isLoading } = useProposals("pending");
  const approve = useApproveProposal();
  const reject = useRejectProposal();
  const approveBatch = useApproveBatch();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const items = data?.items ?? [];
  const selected = items.find((p) => p.id === selectedId) ?? items[0];

  function approveAll() {
    if (!items.length) return;
    if (!window.confirm(`Approve all ${items.length} pending proposals?`)) return;
    void approveBatch.mutate(items.map((p) => p.id));
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <section className="rounded-lg border border-border bg-card">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Pending proposals</h2>
            <p className="text-xs text-muted-foreground">
              {isLoading ? "Loading..." : `${items.length} pending`}
            </p>
          </div>
          <button
            type="button"
            onClick={approveAll}
            disabled={items.length === 0 || approveBatch.isPending}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-50"
          >
            {approveBatch.isPending ? "Approving..." : "Approve all"}
          </button>
        </header>
        <ul className="max-h-[70vh] divide-y divide-border overflow-y-auto">
          {items.length === 0 ? (
            <li className="px-4 py-8 text-center text-sm text-muted-foreground">
              No pending proposals. Ask the chat agent to file some.
            </li>
          ) : null}
          {items.map((p) => (
            <li
              key={p.id}
              className={cn(
                "cursor-pointer px-4 py-2 hover:bg-muted",
                selected?.id === p.id ? "bg-muted" : "",
                highlightIds.includes(p.id) ? "border-l-2 border-primary" : "",
              )}
              onClick={() => setSelectedId(p.id)}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs">
                  {p.action} {p.target_type ?? ""}
                </span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px]",
                    STATUS_PILL[p.status] ?? STATUS_PILL.hidden,
                  )}
                >
                  {p.status}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">{summarize(p)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-border bg-card">
        {selected ? (
          <Detail
            proposal={selected}
            onApprove={() => approve.mutate(selected.id)}
            onReject={() => reject.mutate(selected.id)}
            busy={approve.isPending || reject.isPending}
          />
        ) : (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">
            Select a proposal to see details.
          </div>
        )}
      </section>
    </div>
  );
}

function Detail({
  proposal,
  onApprove,
  onReject,
  busy,
}: {
  proposal: ProposalRow;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-foreground">
            {proposal.action} {proposal.target_type ?? "(no target type)"}
          </div>
          <div className="text-xs text-muted-foreground">
            id {proposal.id.slice(0, 8)} - confidence {proposal.confidence}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onReject}
            disabled={busy || proposal.status !== "pending"}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy || proposal.status !== "pending"}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-50"
          >
            Approve
          </button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-4">
        {proposal.apply_error ? (
          <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            <span className="font-semibold">Apply error: </span>
            {proposal.apply_error}
          </div>
        ) : null}
        <ProposalDiff proposal={proposal} />
      </div>
    </div>
  );
}

function summarize(p: ProposalRow): string {
  const payload = p.payload ?? {};
  if (typeof payload.display_name === "string") return payload.display_name;
  if (typeof payload.name === "string") return payload.name;
  if (typeof payload.title === "string") return payload.title;
  if (typeof payload.type === "string") return payload.type;
  return p.rationale ?? "";
}
