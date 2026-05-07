/**
 * Tests for the name parsing helpers (initials, nickname extraction, and
 * given_names round-trip). These keep the avatar badge and the drawer's
 * Nickname row working when the backend sends partial structured fields.
 */

import { describe, expect, it } from "vitest";

import { parseName, personInitials, rebuildGivenNames, formatNameWithNickname } from "@/lib/names";

describe("personInitials", () => {
  it("uses given + surname when both are present", () => {
    expect(personInitials({ display_name: "Bob Lee", given_names: "Bob", surname: "Lee" })).toBe(
      "BL",
    );
  });

  it("falls back to display name for the first initial when given_names is missing", () => {
    expect(personInitials({ display_name: "Bob Lee", given_names: null, surname: "Lee" })).toBe(
      "BL",
    );
  });

  it("falls back to display name for the last initial when surname is missing", () => {
    expect(personInitials({ display_name: "Bob Lee", given_names: "Bob", surname: null })).toBe(
      "BL",
    );
  });

  it("falls back to display name for both initials when given_names + surname are missing", () => {
    expect(personInitials({ display_name: "Bob Lee", given_names: null, surname: null })).toBe(
      "BL",
    );
  });

  it("returns just the first initial for a single-token display name", () => {
    expect(personInitials({ display_name: "Bob", given_names: null, surname: null })).toBe("B");
  });

  it("skips quoted nicknames when computing initials", () => {
    expect(
      personInitials({
        display_name: 'John "Jonny" Smith',
        given_names: 'John "Jonny"',
        surname: "Smith",
      }),
    ).toBe("JS");
  });

  it("returns ? when no name is recoverable", () => {
    expect(personInitials({ display_name: "", given_names: null, surname: null })).toBe("?");
  });
});

describe("parseName + rebuildGivenNames round-trip", () => {
  it("extracts a quoted nickname from given_names", () => {
    const parsed = parseName('John "Jonny"', "Smith");
    expect(parsed.first).toBe("John");
    expect(parsed.middle).toBe(null);
    expect(parsed.nicknames).toEqual(["Jonny"]);
    expect(parsed.surname).toBe("Smith");
  });

  it("supports parens and single-quote nickname conventions", () => {
    expect(parseName("Mary 'Polly'", "Jones").nicknames).toEqual(["Polly"]);
    expect(parseName("Robert (Bob)", "Lee").nicknames).toEqual(["Bob"]);
  });

  it("rebuilds given_names with nicknames as quoted tokens", () => {
    expect(rebuildGivenNames("John", "Quincy", ["Jonny"])).toBe('John Quincy "Jonny"');
    expect(rebuildGivenNames("Mary", null, ["Polly", "Maisie"])).toBe('Mary "Polly" "Maisie"');
    expect(rebuildGivenNames(null, null, [])).toBe(null);
  });
});

describe("formatNameWithNickname", () => {
  it("inlines the first nickname when display_name is plain", () => {
    expect(
      formatNameWithNickname({
        display_name: "John Smith",
        given_names: 'John "Jonny"',
        surname: "Smith",
      }),
    ).toBe('John "Jonny" Smith');
  });

  it("leaves display_name alone when it already contains the nickname", () => {
    expect(
      formatNameWithNickname({
        display_name: 'John "Jonny" Smith',
        given_names: 'John "Jonny"',
        surname: "Smith",
      }),
    ).toBe('John "Jonny" Smith');
  });
});
