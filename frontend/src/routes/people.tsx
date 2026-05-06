import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { usePeople } from "@/api/endpoints/people";

export const Route = createFileRoute("/people")({
  component: PeoplePage,
});

function PeoplePage() {
  const [q, setQ] = useState("");
  const { data, isLoading } = usePeople(q);
  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">People</h1>
      <input
        className="mt-3 w-full max-w-md rounded border border-zinc-300 px-3 py-2"
        placeholder="Search by name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="mt-4">
        {isLoading ? <p>Loading...</p> : null}
        <ul className="divide-y divide-zinc-200">
          {(data?.items ?? []).map((person) => (
            <li key={person.id} className="py-2">
              <div className="font-medium">{person.display_name}</div>
              <div className="text-xs text-zinc-500">{person.sex}</div>
            </li>
          ))}
        </ul>
        {data?.items.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">
            No people yet. Upload a GEDCOM to populate the tree.
          </p>
        ) : null}
      </div>
    </section>
  );
}
