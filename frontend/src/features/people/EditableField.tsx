/**
 * Hover-to-reveal pencil icon, click to edit. On Enter or blur the value is
 * patched via the supplied save callback. Escape cancels. Used throughout the
 * People drawer for inline edits without modal forms.
 */

import { Check, Loader2, Pencil, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Props =
  | {
      label: string;
      value: string | null | undefined;
      onSave: (value: string | null) => Promise<unknown>;
      placeholder?: string;
      multiline?: boolean;
      saving?: boolean;
      readonly?: boolean;
      tooltip?: ReactNode;
      type?: "text";
      options?: never;
    }
  | {
      label: string;
      value: string | null | undefined;
      onSave: (value: string | null) => Promise<unknown>;
      placeholder?: string;
      multiline?: boolean;
      saving?: boolean;
      readonly?: boolean;
      tooltip?: ReactNode;
      type: "select";
      options: { value: string; label: string }[];
    }
  | {
      label: string;
      value: boolean | null | undefined;
      onSave: (value: boolean) => Promise<unknown>;
      placeholder?: never;
      multiline?: never;
      saving?: boolean;
      readonly?: boolean;
      tooltip?: ReactNode;
      type: "boolean";
      options?: never;
    };

export function EditableField(props: Props) {
  const { label, value, saving, readonly, tooltip, type } = props;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(typeof value === "string" ? value : "");
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null);

  useEffect(() => {
    if (!editing) setDraft(typeof value === "string" ? value : "");
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  async function commit(next: string | null) {
    if (props.type === "boolean") return;
    const candidate = (next ?? "").trim();
    const current = (typeof value === "string" ? value : "").trim();
    if (candidate === current) {
      setEditing(false);
      return;
    }
    // Empty string -> null so the backend can clear the field; non-empty
    // strings flow through unchanged. Without the trim() + ternary the old
    // implementation always sent null due to JS operator precedence
    // (`a ?? "" === "" ? null : a` parses as `(a ?? true) ? null : a`).
    await props.onSave(candidate === "" ? null : candidate);
    setEditing(false);
  }

  if (type === "boolean") {
    return (
      <FieldShell label={label} tooltip={tooltip}>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={saving || readonly}
            onChange={async (e) => {
              await props.onSave(e.target.checked);
            }}
            className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
          />
          <span className="text-zinc-700">{value ? "Living" : "Deceased"}</span>
          {saving ? <Loader2 className="h-3 w-3 animate-spin text-zinc-400" /> : null}
        </label>
      </FieldShell>
    );
  }

  if (!editing) {
    return (
      <FieldShell label={label} tooltip={tooltip}>
        <button
          type="button"
          onClick={() => !readonly && setEditing(true)}
          disabled={readonly}
          className={cn(
            "group flex w-full items-start gap-2 rounded text-left text-sm",
            readonly ? "cursor-default" : "cursor-text hover:bg-zinc-50",
          )}
        >
          <span className={cn("flex-1", value ? "text-zinc-900" : "italic text-zinc-400")}>
            {typeof value === "string" && value ? value : "—"}
          </span>
          {!readonly ? (
            <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-zinc-300 opacity-0 transition-opacity group-hover:opacity-100" />
          ) : null}
        </button>
      </FieldShell>
    );
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setEditing(false);
      setDraft(typeof value === "string" ? value : "");
    } else if (e.key === "Enter" && !e.shiftKey && !props.multiline) {
      e.preventDefault();
      void commit(draft.trim() || null);
    }
  };

  return (
    <FieldShell label={label} tooltip={tooltip}>
      <div className="flex items-start gap-1">
        {type === "select" ? (
          <select
            ref={(el) => {
              inputRef.current = el;
            }}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void commit(draft || null)}
            onKeyDown={onKeyDown}
            disabled={saving}
            className="flex-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">—</option>
            {props.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        ) : props.multiline ? (
          <textarea
            ref={(el) => {
              inputRef.current = el;
            }}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void commit(draft.trim() || null)}
            onKeyDown={onKeyDown}
            disabled={saving}
            placeholder={props.placeholder}
            rows={3}
            className="flex-1 resize-y rounded border border-zinc-300 bg-white px-2 py-1 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        ) : (
          <input
            ref={(el) => {
              inputRef.current = el;
            }}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void commit(draft.trim() || null)}
            onKeyDown={onKeyDown}
            disabled={saving}
            placeholder={props.placeholder}
            className="flex-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        )}
        <button
          type="button"
          onMouseDown={(e) => {
            e.preventDefault();
            void commit(draft.trim() || null);
          }}
          disabled={saving}
          className="rounded border border-emerald-300 bg-emerald-50 p-1 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
          aria-label="Save"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
        </button>
        <button
          type="button"
          onMouseDown={(e) => {
            e.preventDefault();
            setEditing(false);
            setDraft(typeof value === "string" ? value : "");
          }}
          disabled={saving}
          className="rounded border border-zinc-300 bg-white p-1 text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          aria-label="Cancel"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </FieldShell>
  );
}

function FieldShell({
  label,
  tooltip,
  children,
}: {
  label: string;
  tooltip?: ReactNode;
  children: ReactNode;
}) {
  const labelEl = (
    <span
      className={cn(
        "text-[11px] font-semibold uppercase tracking-wide text-zinc-500",
        tooltip ? "border-b border-dotted border-zinc-300 cursor-help" : "",
      )}
    >
      {label}
    </span>
  );
  return (
    <div>
      <div className="mb-1">{tooltip ? <Tooltip content={tooltip}>{labelEl}</Tooltip> : labelEl}</div>
      {children}
    </div>
  );
}
