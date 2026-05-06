import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/tree")({
  component: TreePage,
});

function TreePage() {
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Family Tree</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Interactive tree visualization (react-flow + dagre layout) lands in the next iteration.
      </p>
    </section>
  );
}
