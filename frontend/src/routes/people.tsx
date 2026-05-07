import { createFileRoute } from "@tanstack/react-router";
import { FileText, Network, Search, Users } from "lucide-react";
import { useState } from "react";

import { usePeople, type PersonRow } from "@/api/endpoints/people";
import { PersonDrawer } from "@/features/people/PersonDrawer";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/people")({
  component: PeoplePage,
});

function PeoplePage() {
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading } = usePeople(q || undefined);
  const people = data?.items ?? [];

  return (
    <section className="flex h-full flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-indigo-600" />
          <h1 className="text-xl font-semibold">People</h1>
          <span className="ml-1 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600">
            {people.length}
          </span>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          Click a row to open the side drawer with notes, relationships, and the documents that reference them.
        </p>
        <div className="mt-3 max-w-md">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-400" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name (uses trigram similarity, so misspellings are okay)"
              className="w-full rounded-md border border-zinc-300 bg-white pl-8 pr-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-auto bg-zinc-50">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center text-sm text-zinc-500">Loading...</div>
        ) : people.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
            {q ? "No matches." : "No people yet. Use the Chat to add some."}
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-zinc-50 text-[11px] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="border-b border-zinc-200 px-4 py-2 text-left font-medium">Name</th>
                <th className="border-b border-zinc-200 px-4 py-2 text-left font-medium">Sex</th>
                <th className="border-b border-zinc-200 px-4 py-2 text-left font-medium">Birth</th>
                <th className="border-b border-zinc-200 px-4 py-2 text-left font-medium">Death</th>
                <th className="border-b border-zinc-200 px-4 py-2 text-left font-medium">Status</th>
                <th className="border-b border-zinc-200 px-4 py-2 text-right font-medium">
                  <span className="inline-flex items-center gap-1">
                    <Network className="h-3 w-3" />
                    Rels
                  </span>
                </th>
                <th className="border-b border-zinc-200 px-4 py-2 text-right font-medium">
                  <span className="inline-flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    Docs
                  </span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white">
              {people.map((p) => (
                <Row
                  key={p.id}
                  person={p}
                  selected={selectedId === p.id}
                  onClick={() => setSelectedId(p.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <PersonDrawer personId={selectedId} onClose={() => setSelectedId(null)} />
    </section>
  );
}

function Row({
  person,
  selected,
  onClick,
}: {
  person: PersonRow;
  selected: boolean;
  onClick: () => void;
}) {
  const sexClass =
    person.sex === "male"
      ? "bg-sky-100 text-sky-700"
      : person.sex === "female"
        ? "bg-rose-100 text-rose-700"
        : "bg-zinc-100 text-zinc-600";
  return (
    <tr
      onClick={onClick}
      className={cn(
        "cursor-pointer transition-colors hover:bg-indigo-50/40",
        selected ? "bg-indigo-50/60" : "",
      )}
    >
      <td className="px-4 py-2">
        <div className="font-medium text-zinc-900">{person.display_name}</div>
        {person.surname && person.given_names ? (
          <div className="text-[11px] text-zinc-500">
            {person.given_names} {person.surname}
          </div>
        ) : null}
      </td>
      <td className="px-4 py-2">
        <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold", sexClass)}>
          {person.sex}
        </span>
      </td>
      <td className="px-4 py-2 text-zinc-700">{person.birth_text || <span className="text-zinc-400">—</span>}</td>
      <td className="px-4 py-2 text-zinc-700">
        {person.death_text || (
          <span className="text-zinc-400">{person.is_living ? "—" : "deceased"}</span>
        )}
      </td>
      <td className="px-4 py-2">
        <span
          className={cn(
            "inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium",
            person.status === "active"
              ? "bg-emerald-50 text-emerald-700"
              : person.status === "hidden"
                ? "bg-zinc-100 text-zinc-500"
                : "bg-amber-50 text-amber-700",
          )}
        >
          {person.status}
        </span>
      </td>
      <td className="px-4 py-2 text-right tabular-nums">
        <span
          className={cn(
            "inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1.5 text-[11px] font-medium",
            person.relationship_count > 0 ? "bg-indigo-50 text-indigo-700" : "text-zinc-400",
          )}
        >
          {person.relationship_count}
        </span>
      </td>
      <td className="px-4 py-2 text-right tabular-nums">
        <span
          className={cn(
            "inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1.5 text-[11px] font-medium",
            person.document_count > 0 ? "bg-emerald-50 text-emerald-700" : "text-zinc-400",
          )}
        >
          {person.document_count}
        </span>
      </td>
    </tr>
  );
}
