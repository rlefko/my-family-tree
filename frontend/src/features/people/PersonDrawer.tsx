/**
 * Right-side drawer for a single person. Three tabs: Details, Relationships,
 * Documents. Footer has Add Note, Add Relationship, and Delete actions.
 *
 * All write actions go through the proposal flow on the server but auto-apply
 * since the user clicked Save / Confirm here.
 */

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  useAddRelationship,
  useAppendNote,
  useDeletePerson,
  usePeople,
  usePerson,
  usePersonDocuments,
  usePersonRelationships,
  type RelationshipEdge,
} from "@/api/endpoints/people";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

const REL_TYPES: { value: string; label: string; symmetric?: boolean }[] = [
  { value: "parent_of", label: "Parent of" },
  { value: "spouse_of", label: "Spouse of", symmetric: true },
  { value: "partner_of", label: "Partner of", symmetric: true },
  { value: "sibling_of", label: "Sibling of", symmetric: true },
  { value: "adoptive_parent_of", label: "Adoptive parent of" },
  { value: "step_parent_of", label: "Step-parent of" },
  { value: "guardian_of", label: "Guardian of" },
];

type Tab = "details" | "relationships" | "documents";

export function PersonDrawer({
  personId,
  onClose,
}: {
  personId: string | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("details");
  const open = personId !== null;

  return (
    <Drawer
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DrawerContent>
        {personId ? <DrawerBody personId={personId} tab={tab} setTab={setTab} /> : null}
      </DrawerContent>
    </Drawer>
  );
}

function DrawerBody({
  personId,
  tab,
  setTab,
}: {
  personId: string;
  tab: Tab;
  setTab: (t: Tab) => void;
}) {
  const detail = usePerson(personId);
  const rels = usePersonRelationships(personId);
  const docs = usePersonDocuments(personId);
  const deleteMutation = useDeletePerson();
  const noteMutation = useAppendNote();
  const addRelMutation = useAddRelationship();
  const allPeople = usePeople();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [adding, setAdding] = useState(false);

  if (detail.isLoading || !detail.data) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading person...
      </div>
    );
  }

  const p = detail.data;

  return (
    <>
      <DrawerHeader className="pr-12">
        <DrawerTitle>{p.display_name}</DrawerTitle>
        <DrawerDescription>
          {[p.given_names, p.surname].filter(Boolean).join(" ") || "No structured name"}
          {" • "}
          <span className="capitalize">{p.sex}</span>
          {p.is_living ? " • Living" : " • Deceased"}
        </DrawerDescription>
      </DrawerHeader>

      <nav className="flex border-b border-zinc-200 px-6">
        {(
          [
            ["details", "Details"],
            ["relationships", `Relationships${rels.data ? ` · ${rels.data.items.length}` : ""}`],
            ["documents", `Documents${docs.data ? ` · ${docs.data.items.length}` : ""}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "border-b-2 px-3 py-2 text-xs font-medium transition-colors",
              tab === key
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-zinc-500 hover:text-zinc-900",
            )}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {tab === "details" ? (
          <DetailsPanel person={p} />
        ) : tab === "relationships" ? (
          <RelationshipsPanel
            personId={personId}
            edges={rels.data?.items ?? []}
            loading={rels.isLoading}
            onAdd={() => setAdding(true)}
            people={(allPeople.data?.items ?? []).filter((x) => x.id !== personId)}
            adding={adding}
            onCancel={() => setAdding(false)}
            onSubmit={(args) => {
              addRelMutation.mutate(args, {
                onSuccess: () => setAdding(false),
              });
            }}
            submitting={addRelMutation.isPending}
          />
        ) : (
          <DocumentsPanel docs={docs.data?.items ?? []} loading={docs.isLoading} />
        )}
      </div>

      <footer className="border-t border-zinc-200 bg-zinc-50 px-6 py-3 space-y-2">
        <div>
          <label htmlFor="add-note" className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            Add a note
          </label>
          <div className="mt-1 flex gap-2">
            <textarea
              id="add-note"
              rows={2}
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              placeholder="Markdown is supported. Saved as a fresh note appended to the person's notes."
              className="flex-1 resize-none rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={() => {
                const text = noteDraft.trim();
                if (!text) return;
                noteMutation.mutate(
                  { personId, text },
                  { onSuccess: () => setNoteDraft("") },
                );
              }}
              disabled={!noteDraft.trim() || noteMutation.isPending}
              className="self-stretch rounded-md bg-indigo-600 px-3 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              Save
            </button>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete person
          </button>
        </div>
      </footer>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete ${p.display_name}?`}
        description="This soft-deletes the person (status becomes hidden). Their relationships and claims stay in place for the audit trail. You can restore them from the database if needed."
        confirmLabel="Delete"
        busy={deleteMutation.isPending}
        onConfirm={() => {
          deleteMutation.mutate(personId, { onSuccess: () => setConfirmOpen(false) });
        }}
      />
    </>
  );
}

function DetailsPanel({
  person,
}: {
  person: ReturnType<typeof usePerson>["data"] extends infer D ? NonNullable<D> : never;
}) {
  return (
    <div className="space-y-4">
      <Field label="Display name" value={person.display_name} />
      <Field label="Given names" value={person.given_names} />
      <Field label="Surname" value={person.surname} />
      <Field label="Surname at birth" value={person.surname_at_birth} />
      <Field label="Suffix" value={person.suffix} />
      <Field label="Sex" value={person.sex} />
      <Field label="Birth" value={person.birth_text} />
      <Field label="Death" value={person.death_text} />
      <Field label="Status" value={person.status} />
      <Field label="Aliases" value={person.aliases.length ? person.aliases.join(", ") : null} />
      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          Notes
        </div>
        {person.notes_md ? (
          <div className="prose-chat rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-800">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{person.notes_md}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-xs italic text-zinc-400">No notes yet.</div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-900">{value || <span className="italic text-zinc-400">—</span>}</div>
    </div>
  );
}

function relationshipPhrase(edge: RelationshipEdge): string {
  const label: Record<string, [string, string]> = {
    parent_of: ["Parent of", "Child of"],
    spouse_of: ["Spouse of", "Spouse of"],
    sibling_of: ["Sibling of", "Sibling of"],
    partner_of: ["Partner of", "Partner of"],
    adoptive_parent_of: ["Adoptive parent of", "Adoptive child of"],
    step_parent_of: ["Step-parent of", "Step-child of"],
    guardian_of: ["Guardian of", "Ward of"],
  };
  const pair = label[edge.type] ?? [edge.type, edge.type];
  return edge.direction === "outgoing" ? pair[0] : pair[1];
}

function RelationshipsPanel({
  personId,
  edges,
  loading,
  onAdd,
  people,
  adding,
  onCancel,
  onSubmit,
  submitting,
}: {
  personId: string;
  edges: RelationshipEdge[];
  loading: boolean;
  onAdd: () => void;
  people: { id: string; display_name: string }[];
  adding: boolean;
  onCancel: () => void;
  onSubmit: (input: {
    personId: string;
    otherId: string;
    type: string;
    direction: "outgoing" | "incoming";
  }) => void;
  submitting: boolean;
}) {
  const grouped = useMemo(() => {
    const buckets = new Map<string, RelationshipEdge[]>();
    for (const e of edges) {
      const phrase = relationshipPhrase(e);
      const list = buckets.get(phrase) ?? [];
      list.push(e);
      buckets.set(phrase, list);
    }
    return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [edges]);

  return (
    <div className="space-y-4">
      {loading ? (
        <div className="text-xs text-zinc-500">Loading...</div>
      ) : edges.length === 0 ? (
        <div className="rounded-md border border-dashed border-zinc-300 bg-white p-4 text-center text-xs text-zinc-500">
          No relationships yet.
        </div>
      ) : (
        grouped.map(([phrase, items]) => (
          <div key={phrase}>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              {phrase}
            </div>
            <ul className="space-y-1">
              {items.map((e) => (
                <li
                  key={e.id}
                  className="flex items-center justify-between rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs"
                >
                  <span className="font-medium text-zinc-900">{e.other.display_name}</span>
                  <span className="text-[10px] uppercase tracking-wide text-zinc-400">
                    {e.confidence}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}

      {adding ? (
        <AddRelationshipForm
          people={people}
          onCancel={onCancel}
          submitting={submitting}
          onSubmit={(otherId, type, direction) =>
            onSubmit({ personId, otherId, type, direction })
          }
        />
      ) : (
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm hover:bg-zinc-50"
        >
          <Plus className="h-3.5 w-3.5" />
          Add relationship
        </button>
      )}
    </div>
  );
}

function AddRelationshipForm({
  people,
  onSubmit,
  onCancel,
  submitting,
}: {
  people: { id: string; display_name: string }[];
  onSubmit: (otherId: string, type: string, direction: "outgoing" | "incoming") => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [type, setType] = useState("parent_of");
  const [direction, setDirection] = useState<"outgoing" | "incoming">("outgoing");
  const [otherId, setOtherId] = useState("");
  const symmetric = REL_TYPES.find((t) => t.value === type)?.symmetric;

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3">
      <div className="space-y-2 text-xs">
        <label className="block">
          <span className="text-zinc-600">Relationship</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs"
          >
            {REL_TYPES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        {!symmetric ? (
          <label className="block">
            <span className="text-zinc-600">Direction</span>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "outgoing" | "incoming")}
              className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs"
            >
              <option value="outgoing">This person → other</option>
              <option value="incoming">Other → this person</option>
            </select>
          </label>
        ) : null}
        <label className="block">
          <span className="text-zinc-600">Other person</span>
          <select
            value={otherId}
            onChange={(e) => setOtherId(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs"
          >
            <option value="">Select...</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded border border-zinc-300 bg-white px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => otherId && onSubmit(otherId, type, direction)}
          disabled={!otherId || submitting}
          className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {submitting ? "Adding..." : "Add"}
        </button>
      </div>
    </div>
  );
}

function DocumentsPanel({
  docs,
  loading,
}: {
  docs: { id: string; title: string | null; kind: string; citation: string | null; claim_count: number }[];
  loading: boolean;
}) {
  if (loading) return <div className="text-xs text-zinc-500">Loading...</div>;
  if (docs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-zinc-300 bg-white p-4 text-center text-xs text-zinc-500">
        No documents reference this person yet.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {docs.map((d) => (
        <li
          key={d.id}
          className="flex items-start justify-between gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs"
        >
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-zinc-900">{d.title ?? "(untitled)"}</div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-400">{d.kind}</div>
            {d.citation ? <div className="mt-0.5 text-zinc-600">{d.citation}</div> : null}
          </div>
          <span className="shrink-0 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700">
            {d.claim_count} claim{d.claim_count === 1 ? "" : "s"}
          </span>
        </li>
      ))}
    </ul>
  );
}
