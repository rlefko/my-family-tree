import { createFileRoute } from "@tanstack/react-router";
import { Loader2, Network } from "lucide-react";

import { useTreeGraph } from "@/api/endpoints/relationships";
import { FamilyTreeGraph } from "@/features/tree/FamilyTreeGraph";

export const Route = createFileRoute("/tree")({
  component: TreePage,
});

function TreePage() {
  const { data, isLoading, isError, error } = useTreeGraph();

  return (
    <section className="flex h-full flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <div className="flex items-center gap-2">
          <Network className="h-5 w-5 text-indigo-600" />
          <h1 className="text-xl font-semibold">Family Tree</h1>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Parent edges run vertically; spouse and partner edges connect horizontally. Sibling
          edges are dashed. Layout updates automatically as you approve proposals.
        </p>
      </header>
      <div className="flex-1">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading tree...
          </div>
        ) : isError ? (
          <div className="flex h-full items-center justify-center p-10 text-center text-sm text-red-600">
            Failed to load tree: {(error as Error)?.message ?? "unknown error"}
          </div>
        ) : data ? (
          <FamilyTreeGraph graph={data} />
        ) : null}
      </div>
    </section>
  );
}
