/**
 * Unit tests for the FamilyTreeGraph layout. We assert two things that the
 * ancestry-style rendering depends on:
 *
 *   1. Spouses get folded into a single union node, and shared children
 *      receive ONE edge from the union (not two from each spouse).
 *   2. Sibling_of edges are not rendered (they're implied by shared parents).
 */

import { describe, expect, it } from "vitest";

import { buildLayout } from "@/features/tree/FamilyTreeGraph";

const personA = {
  id: "p-a",
  display_name: "Alice",
  surname: "X",
  sex: "female" as const,
  birth_text: null,
  death_text: null,
  is_living: true,
};
const personB = {
  id: "p-b",
  display_name: "Bob",
  surname: "X",
  sex: "male" as const,
  birth_text: null,
  death_text: null,
  is_living: true,
};
const personC = {
  id: "p-c",
  display_name: "Susan",
  surname: "X",
  sex: "female" as const,
  birth_text: null,
  death_text: null,
  is_living: true,
};
const personD = {
  id: "p-d",
  display_name: "Dan",
  surname: "X",
  sex: "male" as const,
  birth_text: null,
  death_text: null,
  is_living: true,
};

describe("buildLayout (family tree)", () => {
  it("inserts a union node for spouses and routes shared children through it", () => {
    const { nodes, edges } = buildLayout({
      persons: [personA, personB, personC],
      relationships: [
        {
          id: "r-spouse",
          subject_id: "p-a",
          object_id: "p-b",
          type: "spouse_of",
          confidence: 100,
        },
        // mirror row stored by the backend for symmetric edges
        {
          id: "r-spouse-mirror",
          subject_id: "p-b",
          object_id: "p-a",
          type: "spouse_of",
          confidence: 100,
        },
        {
          id: "r-parent-a",
          subject_id: "p-a",
          object_id: "p-c",
          type: "parent_of",
          confidence: 100,
        },
        {
          id: "r-parent-b",
          subject_id: "p-b",
          object_id: "p-c",
          type: "parent_of",
          confidence: 100,
        },
      ],
    });

    const unionNodes = nodes.filter((n) => n.type === "union");
    expect(unionNodes).toHaveLength(1);
    const union = unionNodes[0];

    // Two couple half-edges into the union.
    const coupleEdges = edges.filter((e) => e.target === union.id);
    expect(coupleEdges).toHaveLength(2);

    // Susan receives exactly one parentage edge — from the union, not from A or B individually.
    const carolEdges = edges.filter((e) => e.target === "p-c");
    expect(carolEdges).toHaveLength(1);
    expect(carolEdges[0].source).toBe(union.id);
  });

  it("routes a child of a single parent directly when no couple edge exists", () => {
    const { edges } = buildLayout({
      persons: [personA, personC],
      relationships: [
        {
          id: "r-parent",
          subject_id: "p-a",
          object_id: "p-c",
          type: "parent_of",
          confidence: 100,
        },
      ],
    });
    const carolEdges = edges.filter((e) => e.target === "p-c");
    expect(carolEdges).toHaveLength(1);
    expect(carolEdges[0].source).toBe("p-a");
  });

  it("does not render sibling_of edges; siblings are implied by shared parents", () => {
    const { edges } = buildLayout({
      persons: [personA, personC, personD],
      relationships: [
        {
          id: "r-parent-c",
          subject_id: "p-a",
          object_id: "p-c",
          type: "parent_of",
          confidence: 100,
        },
        {
          id: "r-parent-d",
          subject_id: "p-a",
          object_id: "p-d",
          type: "parent_of",
          confidence: 100,
        },
        {
          id: "r-sibling",
          subject_id: "p-c",
          object_id: "p-d",
          type: "sibling_of",
          confidence: 100,
        },
        {
          id: "r-sibling-mirror",
          subject_id: "p-d",
          object_id: "p-c",
          type: "sibling_of",
          confidence: 100,
        },
      ],
    });
    // Only parent edges should be present (no edge between p-c and p-d).
    const siblingEdges = edges.filter(
      (e) =>
        (e.source === "p-c" && e.target === "p-d") ||
        (e.source === "p-d" && e.target === "p-c"),
    );
    expect(siblingEdges).toHaveLength(0);
  });
});
