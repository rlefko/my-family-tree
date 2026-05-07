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
 * initial. Falls back to just the first-name initial when there's no surname.
 *
 * Tries the structured fields first (`given_names`, `surname`); if either is
 * missing, falls back to the display name parsed as "First [...] Last" — the
 * first token's initial paired with the last token's initial. Never blends
 * middle names or nicknames into the badge.
 */
export function personInitials(p: {
  display_name: string;
  given_names?: string | null;
  surname?: string | null;
}): string {
  const parsed = parseName(p.given_names, p.surname);
  const firstInitial = (parsed.first ?? "")[0]?.toUpperCase() ?? "";

  let lastInitial = (parsed.surname ?? "")[0]?.toUpperCase() ?? "";
  if (!firstInitial && !lastInitial) {
    // Fall back to display name — same convention: first word + last word,
    // skipping any quoted nickname tokens in between.
    const displayParsed = parseName(p.display_name, null);
    const fi = (displayParsed.first ?? "")[0]?.toUpperCase() ?? "";
    const lastFromDisplay = displayParsed.middle?.split(/\s+/).pop() ?? null;
    const li = (lastFromDisplay ?? "")[0]?.toUpperCase() ?? "";
    return `${fi}${li}` || "?";
  }
  if (!lastInitial) {
    const parts = (p.display_name ?? "").trim().split(/\s+/).filter(Boolean);
    if (parts.length > 1) {
      lastInitial = parts[parts.length - 1][0]?.toUpperCase() ?? "";
    }
  }

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
