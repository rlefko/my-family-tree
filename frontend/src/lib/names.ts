/**
 * Name parsing helpers. The backend stores `given_names` as a single string;
 * we split into first + middle pieces client-side for display so the UI can
 * show "First Middle Last" without requiring a schema change.
 */

export type ParsedName = {
  first: string | null;
  middle: string | null;
  surname: string | null;
};

export function parseName(
  given: string | null | undefined,
  surname: string | null | undefined,
): ParsedName {
  const tokens = (given ?? "").trim().split(/\s+/).filter(Boolean);
  return {
    first: tokens[0] ?? null,
    middle: tokens.length > 1 ? tokens.slice(1).join(" ") : null,
    surname: surname || null,
  };
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

/**
 * Build a 1- or 2-character initial badge: first-name initial plus last-name
 * initial. Falls back to just the first-name initial when there's no surname.
 *
 * Tries the structured fields first (`given_names`, `surname`); if either is
 * missing, falls back to the display name parsed as "First [...] Last" — the
 * first token's initial paired with the last token's initial. Never blends
 * middle names into the badge.
 */
export function personInitials(p: {
  display_name: string;
  given_names?: string | null;
  surname?: string | null;
}): string {
  const firstChar = (s: string | null | undefined) =>
    (s ?? "").trim().split(/\s+/)[0]?.[0]?.toUpperCase() ?? "";

  const firstInitial = firstChar(p.given_names) || firstChar(p.display_name);

  let lastInitial = firstChar(p.surname);
  if (!lastInitial) {
    const parts = (p.display_name ?? "").trim().split(/\s+/).filter(Boolean);
    if (parts.length > 1) lastInitial = parts[parts.length - 1][0]?.toUpperCase() ?? "";
  }

  return `${firstInitial}${lastInitial}` || "?";
}

function normalize(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}
