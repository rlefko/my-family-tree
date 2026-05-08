import { createFileRoute } from "@tanstack/react-router";

import { useConflicts } from "@/api/endpoints/conflicts";

export const Route = createFileRoute("/conflicts")({
  component: ConflictsPage,
});

function ConflictsPage() {
  const { data } = useConflicts();
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Conflicts</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Open conflicts surfaced by the rules engine. Resolve them to update the canonical tree.
      </p>
      <ul className="mt-4 space-y-3">
        {(data?.items ?? []).map((c) => (
          <li key={c.id} className="rounded border border-border bg-card p-4 shadow-sm">
            <div className="text-sm font-semibold text-foreground">{c.kind}</div>
            <div className="text-sm text-foreground">{c.summary}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              severity {c.severity} - subject {c.subject_type} {c.subject_id}
            </div>
          </li>
        ))}
      </ul>
      {(data?.items.length ?? 0) === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No open conflicts.</p>
      ) : null}
    </section>
  );
}
