import { createFileRoute } from "@tanstack/react-router";

import { useTreeStats } from "@/api/endpoints/tree";

export const Route = createFileRoute("/")({
  component: Dashboard,
});

function Dashboard() {
  const stats = useTreeStats();
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p className="mt-1 text-sm text-zinc-500">Counts and recent activity for your family tree.</p>
      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-3">
        <Stat label="People" value={stats.data?.persons} />
        <Stat label="Events" value={stats.data?.events} />
        <Stat label="Relationships" value={stats.data?.relationships} />
        <Stat label="Documents" value={stats.data?.documents} />
        <Stat label="Open conflicts" value={stats.data?.conflicts_open} />
        <Stat label="Pending proposals" value={stats.data?.proposals_pending} />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value ?? "-"}</div>
    </div>
  );
}
