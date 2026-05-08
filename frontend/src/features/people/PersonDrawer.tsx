/**
 * Right-side drawer for a single person. Three tabs: Details, Relationships,
 * Documents. Footer holds Add Note and Delete actions; Relationships tab has
 * an inline Add Relationship form.
 *
 * Every visible field on the Details tab is editable in place. Click a value
 * to swap it for an input, Enter to save, Escape to cancel. Each save goes
 * through the proposal flow on the server but auto-applies since the user
 * just confirmed it.
 */

import { Calendar, Loader2, MapPin, Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  useAddEvent,
  useAddRelationship,
  useAppendNote,
  useDeletePerson,
  useDeleteRelationship,
  usePeople,
  usePerson,
  usePersonDocuments,
  usePersonEvents,
  usePersonRelationships,
  useUpdatePerson,
  type EventRow,
  type PersonDetail,
  type RelationshipEdge,
  type UpdatePersonInput,
} from "@/api/endpoints/people";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Tooltip } from "@/components/ui/tooltip";
import { displayMatchesStructured, parseName, rebuildGivenNames } from "@/lib/names";
import { cn } from "@/lib/utils";

import { EditableField } from "./EditableField";

const REL_TYPES: { value: string; label: string; symmetric?: boolean }[] = [
  { value: "parent_of", label: "Parent of" },
  { value: "spouse_of", label: "Spouse of", symmetric: true },
  { value: "partner_of", label: "Partner of", symmetric: true },
  { value: "sibling_of", label: "Sibling of", symmetric: true },
  { value: "adoptive_parent_of", label: "Adoptive parent of" },
  { value: "step_parent_of", label: "Step-parent of" },
  { value: "guardian_of", label: "Guardian of" },
];

const EVENT_TYPES = [
  { value: "marriage", label: "Marriage" },
  { value: "divorce", label: "Divorce" },
  { value: "birth", label: "Birth" },
  { value: "death", label: "Death" },
  { value: "baptism", label: "Baptism" },
  { value: "burial", label: "Burial" },
  { value: "immigration", label: "Immigration" },
  { value: "emigration", label: "Emigration" },
  { value: "residence", label: "Residence" },
  { value: "census", label: "Census" },
  { value: "military", label: "Military" },
  { value: "occupation", label: "Occupation" },
  { value: "education", label: "Education" },
  { value: "religion", label: "Religion" },
  { value: "will", label: "Will" },
  { value: "probate", label: "Probate" },
  { value: "other", label: "Other" },
];

type Tab = "details" | "relationships" | "events" | "documents";

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
        {personId ? (
          <DrawerBody key={personId} personId={personId} tab={tab} setTab={setTab} />
        ) : null}
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
  const events = usePersonEvents(personId);
  const deleteMutation = useDeletePerson();
  const noteMutation = useAppendNote();
  const addRelMutation = useAddRelationship();
  const deleteRelMutation = useDeleteRelationship();
  const addEventMutation = useAddEvent();
  const updateMutation = useUpdatePerson();
  const allPeople = usePeople();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [addingEvent, setAddingEvent] = useState(false);

  if (detail.isLoading || !detail.data) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading person...
      </div>
    );
  }

  const p = detail.data;
  const showStructuredSubtitle = !displayMatchesStructured(p) && (p.given_names || p.surname);

  async function patch(update: UpdatePersonInput) {
    await updateMutation.mutateAsync({ personId, patch: update });
  }

  return (
    <>
      <DrawerHeader className="pr-12">
        <DrawerTitle>{p.display_name}</DrawerTitle>
        {showStructuredSubtitle ? (
          <DrawerDescription>
            {[p.given_names, p.surname].filter(Boolean).join(" ")}
          </DrawerDescription>
        ) : null}
        <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="capitalize">{p.sex}</span>
          <span>·</span>
          <span>{p.is_living ? "Living" : "Deceased"}</span>
          <span>·</span>
          <span className="capitalize">{p.status}</span>
        </div>
      </DrawerHeader>

      <nav className="flex border-b border-border px-6">
        {(
          [
            ["details", "Details"],
            ["relationships", `Relationships${rels.data ? ` · ${rels.data.items.length}` : ""}`],
            ["events", `Events${events.data ? ` · ${events.data.items.length}` : ""}`],
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
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {tab === "details" ? (
          <DetailsPanel person={p} patch={patch} saving={updateMutation.isPending} />
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
              addRelMutation.mutate(args, { onSuccess: () => setAdding(false) });
            }}
            submitting={addRelMutation.isPending}
            onDelete={(id) => deleteRelMutation.mutate(id)}
            deletingId={deleteRelMutation.isPending ? (deleteRelMutation.variables ?? null) : null}
          />
        ) : tab === "events" ? (
          <EventsPanel
            events={events.data?.items ?? []}
            loading={events.isLoading}
            adding={addingEvent}
            onAdd={() => setAddingEvent(true)}
            onCancel={() => setAddingEvent(false)}
            people={(allPeople.data?.items ?? []).filter((x) => x.id !== personId)}
            submitting={addEventMutation.isPending}
            onSubmit={(input) =>
              addEventMutation.mutate(
                { personId, ...input },
                { onSuccess: () => setAddingEvent(false) },
              )
            }
          />
        ) : (
          <DocumentsPanel docs={docs.data?.items ?? []} loading={docs.isLoading} />
        )}
      </div>

      <footer className="space-y-2 border-t border-border bg-muted px-6 py-3">
        <div>
          <label
            htmlFor="add-note"
            className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
          >
            Add a note
          </label>
          <div className="mt-1 flex gap-2">
            <textarea
              id="add-note"
              rows={2}
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              placeholder="Markdown supported. Appended to existing notes with a separator."
              className="flex-1 resize-none rounded-md border border-input bg-background px-2 py-1.5 text-xs shadow-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button
              type="button"
              onClick={() => {
                const text = noteDraft.trim();
                if (!text) return;
                noteMutation.mutate({ personId, text }, { onSuccess: () => setNoteDraft("") });
              }}
              disabled={!noteDraft.trim() || noteMutation.isPending}
              className="self-stretch rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-60"
            >
              Save
            </button>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 bg-background px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10"
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
        description="Soft-deletes the person (status flips to hidden). Their relationships and claims stay in place for the audit trail. You can restore them from the database if needed."
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
  patch,
  saving,
}: {
  person: PersonDetail;
  patch: (input: UpdatePersonInput) => Promise<void>;
  saving: boolean;
}) {
  const parsed = parseName(person.given_names, person.surname);

  return (
    <div className="space-y-3">
      <EditableField
        label="Display name"
        value={person.display_name}
        saving={saving}
        onSave={(v) => patch({ display_name: v })}
        tooltip="The label shown everywhere, usually the full common name."
      />
      <EditableField
        label="First name"
        value={parsed.first}
        saving={saving}
        onSave={async (v) => {
          await patch({ given_names: rebuildGivenNames(v, parsed.middle, parsed.nicknames) });
        }}
      />
      <EditableField
        label="Middle name(s)"
        value={parsed.middle}
        saving={saving}
        onSave={async (v) => {
          await patch({ given_names: rebuildGivenNames(parsed.first, v, parsed.nicknames) });
        }}
        tooltip="Stored as part of given names; we split on whitespace for display."
      />
      <EditableField
        label="Nickname(s)"
        value={parsed.nicknames.join(", ")}
        saving={saving}
        onSave={async (v) => {
          const next =
            (v ?? "")
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean) ?? [];
          await patch({ given_names: rebuildGivenNames(parsed.first, parsed.middle, next) });
        }}
        tooltip={`Comma-separated. Stored as quoted tokens inside given names (e.g., John "Jonny" Smith). The chat agent reads quoted tokens as nicknames automatically.`}
      />
      <EditableField
        label="Surname"
        value={person.surname}
        saving={saving}
        onSave={(v) => patch({ surname: v })}
      />
      <EditableField
        label="Surname at birth"
        value={person.surname_at_birth}
        saving={saving}
        onSave={(v) => patch({ surname_at_birth: v })}
        tooltip="Maiden / pre-marriage / pre-adoption surname, when different."
      />
      <EditableField
        label="Suffix"
        value={person.suffix}
        saving={saving}
        onSave={(v) => patch({ suffix: v })}
        tooltip="Jr., Sr., III, etc."
      />
      <EditableField
        label="Sex"
        value={person.sex}
        saving={saving}
        type="select"
        options={[
          { value: "female", label: "Female" },
          { value: "male", label: "Male" },
          { value: "unknown", label: "Unknown" },
        ]}
        onSave={(v) => patch({ sex: (v as "male" | "female" | "unknown") || "unknown" })}
      />
      <EditableField
        label="Birth date"
        value={person.birth_text}
        saving={saving}
        onSave={(v) => patch({ birth_text: v })}
        tooltip="Free-form date: '1990-04-12', 'April 12 1990', 'circa 1942', '1942-1944' all parse."
      />
      <EditableField
        label="Birth place"
        value={person.birth_place?.name ?? null}
        saving={saving}
        onSave={(v) => patch({ birth_place_text: v })}
        tooltip="Type a place name. New places are created automatically; existing ones are reused."
      />
      <EditableField
        label="Death date"
        value={person.death_text}
        saving={saving}
        onSave={(v) => patch({ death_text: v })}
      />
      <EditableField
        label="Death place"
        value={person.death_place?.name ?? null}
        saving={saving}
        onSave={(v) => patch({ death_place_text: v })}
      />
      <EditableField
        label="Living"
        value={person.is_living}
        saving={saving}
        type="boolean"
        onSave={(v) => patch({ is_living: v })}
      />

      <Field
        label="Aliases"
        value={person.aliases.length ? person.aliases.join(", ") : null}
        tooltip="Other names this person is known by. Add via the chat for now."
      />

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Notes
        </div>
        {person.notes_md ? (
          <div className="prose-chat rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{person.notes_md}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-xs italic text-muted-foreground">
            No notes yet. Use the &ldquo;Add a note&rdquo; box below.
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: string | null | undefined;
  tooltip?: string;
}) {
  const labelEl = (
    <span
      className={cn(
        "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
        tooltip ? "border-b border-dotted border-border cursor-help" : "",
      )}
    >
      {label}
    </span>
  );
  return (
    <div>
      <div className="mb-1">
        {tooltip ? <Tooltip content={tooltip}>{labelEl}</Tooltip> : labelEl}
      </div>
      <div className={cn("text-sm", value ? "text-foreground" : "italic text-muted-foreground")}>
        {value || "-"}
      </div>
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
  onDelete,
  deletingId,
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
  onDelete: (relationshipId: string) => void;
  deletingId: string | null;
}) {
  const grouped = useMemo(() => {
    const buckets = new Map<string, RelationshipEdge[]>();
    for (const e of edges) {
      const phrase = relationshipPhrase(e);
      const list = buckets.get(phrase) ?? [];
      list.push(e);
      buckets.set(phrase, list);
    }
    const entries = [...buckets.entries()];
    entries.sort(([a], [b]) => a.localeCompare(b));
    return entries;
  }, [edges]);

  return (
    <div className="space-y-4">
      {loading ? (
        <div className="text-xs text-muted-foreground">Loading...</div>
      ) : edges.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
          No relationships yet.
        </div>
      ) : (
        grouped.map(([phrase, items]) => (
          <div key={phrase}>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {phrase}
            </div>
            <ul className="space-y-1">
              {items.map((e) => (
                <li
                  key={e.id}
                  className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs"
                >
                  <span className="flex-1 font-medium text-foreground">{e.other.display_name}</span>
                  {e.confidence >= 100 ? null : (
                    <Tooltip
                      content={`Confidence in this relationship: ${e.confidence}/100. 100 means asserted directly by the user; lower numbers reflect inferences from documents or chat.`}
                    >
                      <span className="cursor-help text-[10px] uppercase tracking-wide text-muted-foreground">
                        {e.confidence}%
                      </span>
                    </Tooltip>
                  )}
                  <Tooltip content="Remove this relationship">
                    <button
                      type="button"
                      onClick={() => onDelete(e.id)}
                      disabled={deletingId === e.id}
                      aria-label="Delete relationship"
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                    >
                      {deletingId === e.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <X className="h-3 w-3" />
                      )}
                    </button>
                  </Tooltip>
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
          onSubmit={(otherId, type, direction) => onSubmit({ personId, otherId, type, direction })}
        />
      ) : (
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-sm hover:bg-muted"
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
    <div className="rounded-md border border-border bg-card p-3">
      <div className="space-y-2 text-xs">
        <label className="block">
          <span className="text-muted-foreground">Relationship</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
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
            <span className="text-muted-foreground">Direction</span>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "outgoing" | "incoming")}
              className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
            >
              <option value="outgoing">This person → other</option>
              <option value="incoming">Other → this person</option>
            </select>
          </label>
        ) : null}
        <label className="block">
          <span className="text-muted-foreground">Other person</span>
          <select
            value={otherId}
            onChange={(e) => setOtherId(e.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
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
          className="rounded border border-input bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => otherId && onSubmit(otherId, type, direction)}
          disabled={!otherId || submitting}
          className="rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {submitting ? "Adding..." : "Add"}
        </button>
      </div>
    </div>
  );
}

function EventsPanel({
  events,
  loading,
  adding,
  onAdd,
  onCancel,
  people,
  submitting,
  onSubmit,
}: {
  events: EventRow[];
  loading: boolean;
  adding: boolean;
  onAdd: () => void;
  onCancel: () => void;
  people: { id: string; display_name: string }[];
  submitting: boolean;
  onSubmit: (input: {
    type: string;
    dateText?: string;
    placeText?: string;
    role: string;
    description?: string;
    otherParticipants?: { person_id: string; role: string }[];
  }) => void;
}) {
  return (
    <div className="space-y-3">
      {loading ? (
        <div className="text-xs text-muted-foreground">Loading...</div>
      ) : events.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
          No events yet. Add a marriage, birth, death, divorce, or other event.
        </div>
      ) : (
        <ul className="space-y-2">
          {events.map((ev) => (
            <EventCard key={ev.id} ev={ev} />
          ))}
        </ul>
      )}

      {adding ? (
        <AddEventForm
          people={people}
          onCancel={onCancel}
          submitting={submitting}
          onSubmit={onSubmit}
        />
      ) : (
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-sm hover:bg-muted"
        >
          <Plus className="h-3.5 w-3.5" />
          Add event
        </button>
      )}
    </div>
  );
}

function EventCard({ ev }: { ev: EventRow }) {
  const typeLabel = ev.type.replaceAll("_", " ");
  const co = ev.participants.map((p) => `${p.display_name ?? p.person_id} (${p.role})`).join(", ");
  return (
    <li className="rounded-md border border-border bg-card px-3 py-2 text-xs">
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium capitalize text-foreground">{typeLabel}</span>
        {ev.confidence >= 100 ? null : (
          <Tooltip content={`Confidence in this event: ${ev.confidence}/100.`}>
            <span className="cursor-help text-[10px] uppercase tracking-wide text-muted-foreground">
              {ev.confidence}%
            </span>
          </Tooltip>
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {ev.date_text ? (
          <span className="inline-flex items-center gap-1">
            <Calendar className="h-3 w-3 text-muted-foreground" />
            {ev.date_text}
          </span>
        ) : null}
        {ev.place ? (
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3 text-muted-foreground" />
            {ev.place.name}
          </span>
        ) : null}
        {ev.role ? (
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            this person: {ev.role}
          </span>
        ) : null}
      </div>
      {co ? <div className="mt-1 text-[11px] text-muted-foreground">with {co}</div> : null}
      {ev.description ? (
        <div className="mt-1 text-[11px] italic text-muted-foreground">{ev.description}</div>
      ) : null}
    </li>
  );
}

function AddEventForm({
  people,
  onCancel,
  submitting,
  onSubmit,
}: {
  people: { id: string; display_name: string }[];
  onCancel: () => void;
  submitting: boolean;
  onSubmit: (input: {
    type: string;
    dateText?: string;
    placeText?: string;
    role: string;
    description?: string;
    otherParticipants?: { person_id: string; role: string }[];
  }) => void;
}) {
  const [type, setType] = useState("marriage");
  const [dateText, setDateText] = useState("");
  const [placeText, setPlaceText] = useState("");
  const [otherId, setOtherId] = useState("");
  const [description, setDescription] = useState("");

  const isPaired = type === "marriage" || type === "divorce";
  const role = isPaired ? "spouse" : "principal";
  const otherRole = isPaired ? "spouse" : "principal";

  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="space-y-2 text-xs">
        <label className="block">
          <span className="text-muted-foreground">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
          >
            {EVENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-muted-foreground">Date</span>
          <input
            type="text"
            value={dateText}
            onChange={(e) => setDateText(e.target.value)}
            placeholder="e.g. June 14 1972, circa 1900, 1942-1944"
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </label>
        <label className="block">
          <span className="text-muted-foreground">Place</span>
          <input
            type="text"
            value={placeText}
            onChange={(e) => setPlaceText(e.target.value)}
            placeholder="e.g. Brooklyn, NY"
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </label>
        {isPaired ? (
          <label className="block">
            <span className="text-muted-foreground">Other party</span>
            <select
              value={otherId}
              onChange={(e) => setOtherId(e.target.value)}
              className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
            >
              <option value="">Select...</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="block">
          <span className="text-muted-foreground">Description (optional)</span>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </label>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded border border-input bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() =>
            onSubmit({
              type,
              dateText: dateText.trim() || undefined,
              placeText: placeText.trim() || undefined,
              role,
              description: description.trim() || undefined,
              otherParticipants:
                isPaired && otherId ? [{ person_id: otherId, role: otherRole }] : undefined,
            })
          }
          disabled={submitting || (isPaired && !otherId)}
          className="rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {submitting ? "Adding..." : "Add event"}
        </button>
      </div>
    </div>
  );
}

function DocumentsPanel({
  docs,
  loading,
}: {
  docs: {
    id: string;
    title: string | null;
    kind: string;
    citation: string | null;
    claim_count: number;
  }[];
  loading: boolean;
}) {
  if (loading) return <div className="text-xs text-muted-foreground">Loading...</div>;
  if (docs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
        No documents reference this person yet.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {docs.map((d) => (
        <li
          key={d.id}
          className="flex items-start justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-xs"
        >
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-foreground">{d.title ?? "(untitled)"}</div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{d.kind}</div>
            {d.citation ? <div className="mt-0.5 text-muted-foreground">{d.citation}</div> : null}
          </div>
          <Tooltip
            content={`This document contributed ${d.claim_count} claim${d.claim_count === 1 ? "" : "s"} about this person.`}
          >
            <span className="shrink-0 cursor-help rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
              {d.claim_count} claim{d.claim_count === 1 ? "" : "s"}
            </span>
          </Tooltip>
        </li>
      ))}
    </ul>
  );
}
