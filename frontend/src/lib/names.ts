/**
 * Name parsing helpers. The backend stores `given_names` as a single string;
 * we split into first + middle + nickname pieces client-side so the UI can
 * show "First Middle Last" or "First 'Nickname' Last" without requiring a
 * schema change.
 *
 * Convention: tokens inside quotes (`"Jonny"`, `'Jonny'`) or parens
 * (`(Jonny)`) within `given_names` are interpreted as nicknames. The
 * remaining unquoted tokens are first + middle names.
 */

const NICKNAME_TOKEN = /^(?:"([^"]+)"|'([^']+)'|\(([^)]+)\))$/;

export type ParsedName = {
  first: string | null;
  middle: string | null;
  nicknames: string[];
  surname: string | null;
};

export function parseName(
  given: string | null | undefined,
  surname: string | null | undefined,
): ParsedName {
  const tokens = (given ?? "").trim().split(/\s+/).filter(Boolean);
  const nicknames: string[] = [];
  const plain: string[] = [];
  for (const tok of tokens) {
    const m = tok.match(NICKNAME_TOKEN);
    if (m) {
      nicknames.push((m[1] ?? m[2] ?? m[3] ?? "").trim());
    } else {
      plain.push(tok);
    }
  }
  return {
    first: plain[0] ?? null,
    middle: plain.length > 1 ? plain.slice(1).join(" ") : null,
    nicknames: nicknames.filter(Boolean),
    surname: surname || null,
  };
}

/**
 * Rebuild a single `given_names` string from edited parts. Nicknames are
 * always serialized in double quotes so a round-trip parse recovers them.
 */
export function rebuildGivenNames(
  first: string | null | undefined,
  middle: string | null | undefined,
  nicknames: string[] = [],
): string | null {
  const parts: string[] = [];
  if (first?.trim()) parts.push(first.trim());
  if (middle?.trim()) parts.push(middle.trim());
  for (const nick of nicknames) {
    const v = nick.trim();
    if (v) parts.push(`"${v}"`);
  }
  return parts.length > 0 ? parts.join(" ") : null;
}

/** Build a structured "full name" string from the parts. */
export function structuredFullName(p: {
  given_names?: string | null;
  surname?: string | null;
}): string {
  return [p.given_names, p.surname].filter(Boolean).join(" ").trim();
}

/** Returns true when display_name is just the structured name with no extra info. */
export function displayMatchesStructured(p: {
  display_name: string;
  given_names?: string | null;
  surname?: string | null;
}): boolean {
  const structured = structuredFullName(p);
  if (!structured) return false;
  return normalize(structured) === normalize(p.display_name);
}

function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Build a 1- or 2-character initial badge: first-name initial plus last-name
 * initial. Falls back to just the first-name initial when there's no surname
 * (or vice-versa). Never blends middle names or nicknames into the badge.
 *
 * Resolution order:
 *  - First initial: structured `given_names` → first plain token of display_name
 *  - Last initial:  structured `surname`     → last plain token of display_name
 *
 * Each side falls back independently, so a record with only `surname` set
 * still recovers the first initial from display_name (and vice-versa).
 */
export function personInitials(p: {
  display_name: string;
  given_names?: string | null;
  surname?: string | null;
}): string {
  const parsed = parseName(p.given_names, p.surname);
  const displayParsed = parseName(p.display_name, null);

  const firstSource = parsed.first ?? displayParsed.first;
  const firstInitial = firstSource ? firstSource[0].toUpperCase() : "";

  let lastSource: string | null = parsed.surname;
  if (!lastSource) {
    // displayParsed.middle is the joined non-first plain tokens (nicknames
    // already stripped by parseName). The last one is the surname-equivalent.
    const tail = displayParsed.middle?.split(/\s+/).pop() ?? null;
    lastSource = tail;
  }
  const lastInitial = lastSource ? lastSource[0].toUpperCase() : "";

  return `${firstInitial}${lastInitial}` || "?";
}

/**
 * Format a person's name with their first nickname inline:
 * "John 'Jonny' Smith". Falls back to display_name when no nickname is set.
 */
export function formatNameWithNickname(p: {
  display_name: string;
  given_names?: string | null;
  surname?: string | null;
}): string {
  const parsed = parseName(p.given_names, p.surname);
  if (parsed.nicknames.length === 0) return p.display_name;
  // If display_name already contains the nickname (likely written by the user
  // that way), don't double-wrap.
  if (parsed.nicknames.some((n) => p.display_name.includes(n))) return p.display_name;
  const nick = parsed.nicknames[0];
  const first = parsed.first ?? "";
  const surname = parsed.surname ?? "";
  return [first, `"${nick}"`, surname].filter(Boolean).join(" ");
}
