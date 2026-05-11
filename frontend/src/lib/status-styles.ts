/**
 * Centralized status pill / badge classes shared across proposals, tool calls,
 * and document statuses. Status semantics (amber=pending, emerald=ok/approved,
 * red=failed, zinc=neutral) are universal and intentionally NOT swapped onto
 * theme tokens; they communicate state regardless of the chrome palette.
 *
 * Each entry pairs the light-mode classes with their dark-mode counterparts
 * so the badges remain legible in both modes without duplicating logic in
 * every consumer.
 */

const SOLID = {
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  zinc: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  red: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
  neutral: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-400",
};

const OUTLINE = {
  amber:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
  emerald:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
  red: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
};

/** Solid pill backgrounds for compact status chips. */
export const STATUS_PILL: Record<string, string> = {
  pending: SOLID.amber,
  running: SOLID.amber,
  approved: SOLID.emerald,
  ok: SOLID.emerald,
  ready: SOLID.emerald,
  rejected: SOLID.zinc,
  canceled: SOLID.zinc,
  expired: SOLID.zinc,
  hidden: SOLID.neutral,
  failed: SOLID.red,
  error: SOLID.red,
};

/** Outline-style badges (used by `<Badge variant="outline" />`). */
export const STATUS_BADGE_OUTLINE: Record<string, string> = {
  pending: OUTLINE.amber,
  running: OUTLINE.amber,
  uploaded: OUTLINE.amber,
  queued: OUTLINE.amber,
  parsing: OUTLINE.amber,
  parsed: OUTLINE.amber,
  ocring: OUTLINE.amber,
  ocred: OUTLINE.amber,
  embedding: OUTLINE.amber,
  ready: OUTLINE.emerald,
  approved: OUTLINE.emerald,
  ok: OUTLINE.emerald,
  failed: OUTLINE.red,
  error: OUTLINE.red,
};

/**
 * Inline-row classes for proposal line items (white/zinc/emerald cards
 * stacked in a list). Distinct from the pill set because the row needs a
 * border and a different neutral baseline.
 */
const WITHDRAWN_TONE = "bg-muted border border-border text-muted-foreground line-through";
export const PROPOSAL_ROW_TONE: Record<string, string> = {
  pending: "bg-card border border-border text-foreground dark:bg-card",
  approved:
    "bg-emerald-50 border border-emerald-200 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-200",
  rejected: WITHDRAWN_TONE,
  canceled: WITHDRAWN_TONE,
  expired: "bg-muted border border-border text-muted-foreground",
};
