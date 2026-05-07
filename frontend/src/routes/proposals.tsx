import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/proposals")({
  component: ProposalsPage,
  validateSearch: (search): { ids?: string } => ({
    ids: typeof search.ids === "string" ? search.ids : undefined,
  }),
});

function ProposalsPage() {
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Proposals</h1>
      <p className="mt-1 text-sm text-zinc-500">List + diff + approve coming up.</p>
    </section>
  );
}
