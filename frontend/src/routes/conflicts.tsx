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
      <p className="mt-1 text-sm text-zinc-500">
        Open conflicts surfaced by the rules engine. Resolve them to update the canonical tree.
      </p>
      <ul className="mt-4 space-y-3">
        {(data?.items ?? []).map((c) => (
          <li key={c.id} className="rounded border border-zinc-200 bg-white p-4 shadow-sm">
            <div className="text-sm font-semibold">{c.kind}</div>
            <div className="text-sm">{c.summary}</div>
            <div className="mt-1 text-xs text-zinc-500">
              severity {c.severity} - subject {c.subject_type} {c.subject_id}
            </div>
          </li>
        ))}
      </ul>
      {(data?.items.length ?? 0) === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">No open conflicts.</p>
      ) : null}
    </section>
  );
}
