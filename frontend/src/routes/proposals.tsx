import { createFileRoute } from "@tanstack/react-router";

import { ProposalList } from "@/features/proposals/ProposalList";

export const Route = createFileRoute("/proposals")({
  component: ProposalsPage,
  validateSearch: (search): { ids?: string } => ({
    ids: typeof search.ids === "string" ? search.ids : undefined,
  }),
});

function ProposalsPage() {
  const { ids } = Route.useSearch();
  const highlightIds = ids ? ids.split(",").filter(Boolean) : [];
  return (
    <section className="flex h-full flex-col">
      <header className="border-b border-border bg-card px-6 py-4">
        <h1 className="text-xl font-semibold text-foreground">Proposals</h1>
        <p className="text-xs text-muted-foreground">
          Review and approve pending changes proposed by the chat agent. Approving materializes the
          canonical row and writes a chat-source provenance trail.
        </p>
      </header>
      <div className="flex-1 overflow-y-auto p-6">
        <ProposalList highlightIds={highlightIds} />
      </div>
    </section>
  );
}
