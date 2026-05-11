/**
 * Tests for `applyEvent`'s trace ordering. The chat bubble renders thinking
 * and tool calls in stream order, so the data model has to interleave them
 * correctly: consecutive thinking deltas append to one entry, but a tool
 * call between thinking bursts splits them into two distinct entries.
 */

import { describe, expect, it } from "vitest";

import {
  applyEvent,
  traceSummary,
  type ChatTurn,
  type ThinkingEntry,
  type ToolEntry,
  type TraceEntry,
} from "@/features/chat/ChatStreamProvider";
import { paragraphizeReasoning, stripInlineMarkdown } from "@/features/chat/Trace";

function emptyTurn(): ChatTurn {
  return {
    id: "t1",
    role: "assistant",
    content: "",
    pending: true,
    trace: [],
    proposalIds: [],
  };
}

function feed(
  turn: ChatTurn,
  events: Array<{ type: string; data: Record<string, unknown> }>,
): ChatTurn {
  return events.reduce((acc, e) => applyEvent(acc, e.type, e.data), turn);
}

describe("applyEvent trace ordering", () => {
  it("merges consecutive thinking deltas into a single entry", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "Looking up " } },
      { type: "thinking_delta", data: { text: "Jane Doe" } },
    ]);
    expect(turn.trace).toHaveLength(1);
    const entry = turn.trace?.[0] as ThinkingEntry;
    expect(entry.kind).toBe("thinking");
    expect(entry.text).toBe("Looking up Jane Doe");
  });

  it("starts a new thinking entry after a tool call", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "first thought" } },
      { type: "tool_use_started", data: { id: "call-1", name: "person_search" } },
      { type: "tool_use_finished", data: { id: "call-1", input: { query: "Jane" } } },
      { type: "tool_result", data: { tool_use_id: "call-1", output: { hits: [] } } },
      { type: "thinking_delta", data: { text: "second thought" } },
    ]);
    expect(turn.trace?.map((e) => e.kind)).toEqual(["thinking", "tool", "thinking"]);
    const first = turn.trace?.[0] as ThinkingEntry;
    const second = turn.trace?.[2] as ThinkingEntry;
    expect(first.text).toBe("first thought");
    expect(second.text).toBe("second thought");
    expect(first.id).not.toBe(second.id);
  });

  it("threads tool input and output onto the matching tool entry", () => {
    const turn = feed(emptyTurn(), [
      { type: "tool_use_started", data: { id: "call-1", name: "person_search" } },
      { type: "tool_use_finished", data: { id: "call-1", input: { query: "Jane" } } },
      { type: "tool_result", data: { tool_use_id: "call-1", output: { hits: [{ id: "p" }] } } },
    ]);
    expect(turn.trace).toHaveLength(1);
    const entry = turn.trace?.[0] as ToolEntry;
    expect(entry.kind).toBe("tool");
    expect(entry.name).toBe("person_search");
    expect(entry.input).toEqual({ query: "Jane" });
    expect(entry.output).toEqual({ hits: [{ id: "p" }] });
    expect(entry.status).toBe("ok");
  });

  it("marks the tool entry as error when tool_result is_error is true", () => {
    const turn = feed(emptyTurn(), [
      { type: "tool_use_started", data: { id: "call-1", name: "person_search" } },
      {
        type: "tool_result",
        data: { tool_use_id: "call-1", output: { error: "kaboom" }, is_error: true },
      },
    ]);
    const entry = turn.trace?.[0] as ToolEntry;
    expect(entry.status).toBe("error");
    expect(entry.output).toEqual({ error: "kaboom" });
  });

  it("preserves the order of multiple interleaved tool calls and thinking", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "plan" } },
      { type: "tool_use_started", data: { id: "a", name: "tool_a" } },
      { type: "tool_result", data: { tool_use_id: "a", output: {} } },
      { type: "thinking_delta", data: { text: "review" } },
      { type: "tool_use_started", data: { id: "b", name: "tool_b" } },
      { type: "tool_result", data: { tool_use_id: "b", output: {} } },
      { type: "thinking_delta", data: { text: "wrap up" } },
    ]);
    const summary = (turn.trace ?? []).map((e) =>
      e.kind === "thinking" ? `T(${e.text})` : `tool(${e.name})`,
    );
    expect(summary).toEqual(["T(plan)", "tool(tool_a)", "T(review)", "tool(tool_b)", "T(wrap up)"]);
  });

  it("splits thinking entries across a thinking_break boundary", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "**Considering options**\nLooking at Anna." } },
      { type: "thinking_break", data: {} },
      { type: "thinking_delta", data: { text: "**Queueing**\nDrafting the proposal." } },
    ]);
    expect(turn.trace).toHaveLength(2);
    const first = turn.trace?.[0] as ThinkingEntry;
    const second = turn.trace?.[1] as ThinkingEntry;
    expect(first.kind).toBe("thinking");
    expect(second.kind).toBe("thinking");
    expect(first.text).toBe("**Considering options**\nLooking at Anna.");
    expect(second.text).toBe("**Queueing**\nDrafting the proposal.");
    expect(first.id).not.toBe(second.id);
  });

  it("ignores a thinking_break before any thinking entry exists", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_break", data: {} },
      { type: "thinking_delta", data: { text: "first thought" } },
    ]);
    expect(turn.trace).toHaveLength(1);
    const only = turn.trace?.[0] as ThinkingEntry;
    expect(only.text).toBe("first thought");
  });

  it("collapses repeated thinking_breaks instead of leaving empty entries", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "alpha" } },
      { type: "thinking_break", data: {} },
      { type: "thinking_break", data: {} },
      { type: "thinking_break", data: {} },
      { type: "thinking_delta", data: { text: "beta" } },
    ]);
    expect(turn.trace).toHaveLength(2);
    const [first, second] = turn.trace as [ThinkingEntry, ThinkingEntry];
    expect(first.text).toBe("alpha");
    expect(second.text).toBe("beta");
  });

  it("keeps thinking_break ordering correct when interleaved with tool calls", () => {
    const turn = feed(emptyTurn(), [
      { type: "thinking_delta", data: { text: "plan" } },
      { type: "thinking_break", data: {} },
      { type: "thinking_delta", data: { text: "double-check" } },
      { type: "tool_use_started", data: { id: "a", name: "person_search" } },
      { type: "tool_result", data: { tool_use_id: "a", output: {} } },
      { type: "thinking_delta", data: { text: "wrap up" } },
    ]);
    const summary = (turn.trace ?? []).map((e) =>
      e.kind === "thinking" ? `T(${e.text})` : `tool(${e.name})`,
    );
    expect(summary).toEqual(["T(plan)", "T(double-check)", "tool(person_search)", "T(wrap up)"]);
  });

  it("sets pending=false and proposalIds on done", () => {
    const turn = feed(emptyTurn(), [{ type: "done", data: { proposal_ids: ["pp-1", "pp-2"] } }]);
    expect(turn.pending).toBe(false);
    expect(turn.proposalIds).toEqual(["pp-1", "pp-2"]);
  });
});

const thinking = (text: string): TraceEntry => ({ kind: "thinking", id: "t", text });
const tool = (id: string, name = "tool_x"): TraceEntry => ({
  kind: "tool",
  id,
  name,
  status: "ok",
});

describe("traceSummary", () => {
  it("returns the reasoning-only label when no tools were called", () => {
    expect(traceSummary([thinking("plan")])).toBe("Reasoning");
  });

  it("uses singular tool wording for exactly one tool call", () => {
    expect(traceSummary([thinking("plan"), tool("a")])).toBe("Reasoned and used 1 tool");
  });

  it("pluralizes when multiple tool calls were made", () => {
    expect(traceSummary([thinking("plan"), tool("a"), thinking("review"), tool("b")])).toBe(
      "Reasoned and used 2 tools",
    );
  });

  it("falls back to the reasoning-only label on an empty trace", () => {
    expect(traceSummary([])).toBe("Reasoning");
  });
});

describe("stripInlineMarkdown", () => {
  it("unwraps bold markers", () => {
    expect(stripInlineMarkdown("**Considering options**")).toBe("Considering options");
    expect(stripInlineMarkdown("__bold__")).toBe("bold");
  });

  it("unwraps italic markers", () => {
    expect(stripInlineMarkdown("*hmm*")).toBe("hmm");
    expect(stripInlineMarkdown("_softly_")).toBe("softly");
  });

  it("unwraps inline code", () => {
    expect(stripInlineMarkdown("look at `person_search` first")).toBe(
      "look at person_search first",
    );
  });

  it("strips a leading heading prefix", () => {
    expect(stripInlineMarkdown("# Plan ahead")).toBe("Plan ahead");
    expect(stripInlineMarkdown("### Step three")).toBe("Step three");
  });

  it("strips a leading list-bullet prefix", () => {
    expect(stripInlineMarkdown("- first item")).toBe("first item");
    expect(stripInlineMarkdown("* dash")).toBe("dash");
    expect(stripInlineMarkdown("+ plus")).toBe("plus");
  });

  it("passes plain text through unchanged", () => {
    expect(stripInlineMarkdown("Just searching for Jane Doe.")).toBe(
      "Just searching for Jane Doe.",
    );
  });

  it("trims surrounding whitespace", () => {
    expect(stripInlineMarkdown("   spaced   ")).toBe("spaced");
  });

  it("handles mixed inline markers", () => {
    expect(stripInlineMarkdown("**Considering** *carefully* the `person_search` results")).toBe(
      "Considering carefully the person_search results",
    );
  });
});

describe("paragraphizeReasoning", () => {
  it("promotes a single newline to a blank-line paragraph break", () => {
    expect(paragraphizeReasoning("**Step one**\nLooked up Anna.")).toBe(
      "**Step one**\n\nLooked up Anna.",
    );
  });

  it("collapses a run of newlines to exactly one paragraph break", () => {
    expect(paragraphizeReasoning("a\n\n\nb")).toBe("a\n\nb");
  });

  it("keeps already-paragraphed text unchanged", () => {
    expect(paragraphizeReasoning("a\n\nb")).toBe("a\n\nb");
  });

  it("paragraph-breaks each step in a multi-step reasoning summary", () => {
    const input = "**Step one**\nLooked up Anna.\n**Step two**\nQueued a proposal.";
    expect(paragraphizeReasoning(input)).toBe(
      "**Step one**\n\nLooked up Anna.\n\n**Step two**\n\nQueued a proposal.",
    );
  });

  it("leaves fenced code blocks untouched", () => {
    const input = "before\n```\nline1\nline2\n```\nafter";
    expect(paragraphizeReasoning(input)).toBe("before\n\n```\nline1\nline2\n```\n\nafter");
  });

  it("passes plain single-line text through unchanged", () => {
    expect(paragraphizeReasoning("just one line")).toBe("just one line");
  });

  it("handles an empty string", () => {
    expect(paragraphizeReasoning("")).toBe("");
  });
});
