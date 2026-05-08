/**
 * Unit tests for the FamilyTreeGraph layout. These cover both the structural
 * contract the React surface depends on (union nodes deduped, child edges
 * routed through the union, sibling_of edges suppressed) and the positional
 * invariants the new genealogy layout adds (spouse adjacency, oldest-first
 * sibling ordering, every node has a finite coordinate).
 */

import { describe, expect, it } from "vitest";

import {
  NODE_HEIGHT,
  NODE_WIDTH,
  NODESEP,
  UNION_HEIGHT,
  UNION_WIDTH,
  buildLayout,
} from "@/features/tree/layout";

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

type LayoutNode = { id: string; type?: string; position: { x: number; y: number } };

function findNode(nodes: LayoutNode[], id: string): LayoutNode {
  const node = nodes.find((n) => n.id === id);
  if (!node) throw new Error(`expected node "${id}" in layout`);
  return node;
}

function findUnion(nodes: LayoutNode[]): LayoutNode {
  const node = nodes.find((n) => n.type === "union");
  if (!node) throw new Error("expected at least one union node");
  return node;
}

function expectFinitePosition(node: LayoutNode) {
  expect(Number.isFinite(node.position.x)).toBe(true);
  expect(Number.isFinite(node.position.y)).toBe(true);
}

function makeRel(id: string, subject: string, object: string, type: "parent_of" | "spouse_of") {
  return { id, subject_id: subject, object_id: object, type, confidence: 100 };
}

describe("buildLayout (family tree)", () => {
  it("inserts a union node for spouses and routes shared children through it", () => {
    const { nodes, edges } = buildLayout({
      persons: [personA, personB, personC],
      couple_events: [],
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

    const coupleEdges = edges.filter((e) => e.target === union.id);
    expect(coupleEdges).toHaveLength(2);

    const carolEdges = edges.filter((e) => e.target === "p-c");
    expect(carolEdges).toHaveLength(1);
    expect(carolEdges[0].source).toBe(union.id);
  });

  it("routes a child of a single parent directly when no couple edge exists", () => {
    const { edges } = buildLayout({
      persons: [personA, personC],
      couple_events: [],
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

  it("infers a couple union when two people share a child even without spouse_of", () => {
    const { nodes, edges } = buildLayout({
      persons: [personA, personB, personC],
      couple_events: [],
      relationships: [
        {
          id: "r-pa-pc",
          subject_id: "p-a",
          object_id: "p-c",
          type: "parent_of",
          confidence: 100,
        },
        {
          id: "r-pb-pc",
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

    const carolEdges = edges.filter((e) => e.target === "p-c");
    expect(carolEdges).toHaveLength(1);
    expect(carolEdges[0].source).toBe(union.id);
  });

  it("does not render sibling_of edges; siblings are implied by shared parents", () => {
    const { edges } = buildLayout({
      persons: [personA, personC, personD],
      couple_events: [],
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
    const siblingEdges = edges.filter(
      (e) =>
        (e.source === "p-c" && e.target === "p-d") || (e.source === "p-d" && e.target === "p-c"),
    );
    expect(siblingEdges).toHaveLength(0);
  });

  it("places spouses adjacent with the union heart between them", () => {
    const { nodes } = buildLayout({
      persons: [personA, personB, personC],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-a", object_id: "p-b", type: "spouse_of", confidence: 100 },
        { id: "r2", subject_id: "p-b", object_id: "p-a", type: "spouse_of", confidence: 100 },
        { id: "r3", subject_id: "p-a", object_id: "p-c", type: "parent_of", confidence: 100 },
        { id: "r4", subject_id: "p-b", object_id: "p-c", type: "parent_of", confidence: 100 },
      ],
    });

    const a = findNode(nodes, "p-a");
    const b = findNode(nodes, "p-b");
    const union = findUnion(nodes);

    const aCenter = a.position.x + NODE_WIDTH / 2;
    const bCenter = b.position.x + NODE_WIDTH / 2;
    const unionCenter = union.position.x + UNION_WIDTH / 2;
    const lo = Math.min(aCenter, bCenter);
    const hi = Math.max(aCenter, bCenter);
    expect(unionCenter).toBeGreaterThan(lo);
    expect(unionCenter).toBeLessThan(hi);

    expect(a.position.y).toBe(b.position.y);
    expect(union.position.y).toBe(a.position.y + (NODE_HEIGHT - UNION_HEIGHT) / 2);

    const distance = Math.abs(a.position.x - b.position.x);
    expect(distance).toBe(NODE_WIDTH + NODESEP + UNION_WIDTH + NODESEP);
  });

  it("orders siblings left-to-right by parsed birth year", () => {
    const youngest = { ...personC, id: "p-young", display_name: "Young", birth_text: "1985" };
    const middle = { ...personC, id: "p-mid", display_name: "Middle", birth_text: "1982" };
    const oldest = { ...personC, id: "p-old", display_name: "Oldest", birth_text: "1980" };
    const { nodes } = buildLayout({
      persons: [personA, oldest, middle, youngest],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-a", object_id: "p-old", type: "parent_of", confidence: 100 },
        { id: "r2", subject_id: "p-a", object_id: "p-mid", type: "parent_of", confidence: 100 },
        { id: "r3", subject_id: "p-a", object_id: "p-young", type: "parent_of", confidence: 100 },
      ],
    });
    const xOf = (id: string) => findNode(nodes, id).position.x;
    expect(xOf("p-old")).toBeLessThan(xOf("p-mid"));
    expect(xOf("p-mid")).toBeLessThan(xOf("p-young"));
  });

  it("places undated siblings after dated ones, alphabetical within", () => {
    const dated = { ...personC, id: "p-dated", display_name: "Dated", birth_text: "1900" };
    const zoe = { ...personC, id: "p-zoe", display_name: "Zoe", birth_text: null };
    const alex = { ...personC, id: "p-alex", display_name: "Alex", birth_text: null };
    const { nodes } = buildLayout({
      persons: [personA, dated, zoe, alex],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-a", object_id: "p-dated", type: "parent_of", confidence: 100 },
        { id: "r2", subject_id: "p-a", object_id: "p-zoe", type: "parent_of", confidence: 100 },
        { id: "r3", subject_id: "p-a", object_id: "p-alex", type: "parent_of", confidence: 100 },
      ],
    });
    const xOf = (id: string) => findNode(nodes, id).position.x;
    expect(xOf("p-dated")).toBeLessThan(xOf("p-alex"));
    expect(xOf("p-alex")).toBeLessThan(xOf("p-zoe"));
  });

  it("aligns each generation on a common y", () => {
    const grandpa = { ...personA, id: "p-gp", display_name: "Grandpa" };
    const parent = { ...personB, id: "p-par", display_name: "Parent" };
    const kid = { ...personC, id: "p-kid", display_name: "Kid" };
    const { nodes } = buildLayout({
      persons: [grandpa, parent, kid],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-gp", object_id: "p-par", type: "parent_of", confidence: 100 },
        { id: "r2", subject_id: "p-par", object_id: "p-kid", type: "parent_of", confidence: 100 },
      ],
    });
    const ys = ["p-gp", "p-par", "p-kid"].map((id) => findNode(nodes, id).position.y);
    expect(ys[0]).toBeLessThan(ys[1]);
    expect(ys[1]).toBeLessThan(ys[2]);
  });

  it("renders a parentless sibling cluster on the same y", () => {
    const { nodes } = buildLayout({
      persons: [personC, personD],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-c", object_id: "p-d", type: "sibling_of", confidence: 100 },
        { id: "r2", subject_id: "p-d", object_id: "p-c", type: "sibling_of", confidence: 100 },
      ],
    });
    const c = findNode(nodes, "p-c");
    const d = findNode(nodes, "p-d");
    expect(c.position.y).toBe(d.position.y);
    expectFinitePosition(c);
    expectFinitePosition(d);
  });

  it("places isolated persons at finite coordinates without crashing", () => {
    const lonely = { ...personA, id: "p-lonely", display_name: "Lonely" };
    const { nodes } = buildLayout({
      persons: [lonely],
      couple_events: [],
      relationships: [],
    });
    expect(nodes).toHaveLength(1);
    expectFinitePosition(nodes[0]);
  });

  it("handles a person with two unions across separate sets of children", () => {
    const partner1 = { ...personB, id: "p-w1", display_name: "Wife One" };
    const partner2 = { ...personB, id: "p-w2", display_name: "Wife Two" };
    const kid1 = { ...personC, id: "p-k1", display_name: "Kid One" };
    const kid2 = { ...personC, id: "p-k2", display_name: "Kid Two" };
    const husband = { ...personA, id: "p-h", display_name: "Husband", sex: "male" as const };
    const { nodes, edges } = buildLayout({
      persons: [husband, partner1, partner2, kid1, kid2],
      couple_events: [],
      relationships: [
        { id: "r1", subject_id: "p-h", object_id: "p-w1", type: "spouse_of", confidence: 100 },
        { id: "r2", subject_id: "p-w1", object_id: "p-h", type: "spouse_of", confidence: 100 },
        { id: "r3", subject_id: "p-h", object_id: "p-w2", type: "spouse_of", confidence: 100 },
        { id: "r4", subject_id: "p-w2", object_id: "p-h", type: "spouse_of", confidence: 100 },
        { id: "r5", subject_id: "p-h", object_id: "p-k1", type: "parent_of", confidence: 100 },
        { id: "r6", subject_id: "p-w1", object_id: "p-k1", type: "parent_of", confidence: 100 },
        { id: "r7", subject_id: "p-h", object_id: "p-k2", type: "parent_of", confidence: 100 },
        { id: "r8", subject_id: "p-w2", object_id: "p-k2", type: "parent_of", confidence: 100 },
      ],
    });
    // Husband's card appears exactly once.
    const husbandCards = nodes.filter((n) => n.id === "p-h");
    expect(husbandCards).toHaveLength(1);
    // Two union hearts.
    const unions = nodes.filter((n) => n.type === "union");
    expect(unions).toHaveLength(2);
    // Each kid receives exactly one parent edge sourced from their union.
    for (const kidId of ["p-k1", "p-k2"]) {
      const kidEdges = edges.filter((e) => e.target === kidId);
      expect(kidEdges).toHaveLength(1);
      expect(unions.map((u) => u.id)).toContain(kidEdges[0].source);
    }
    // All five persons get finite positions.
    for (const id of ["p-h", "p-w1", "p-w2", "p-k1", "p-k2"]) {
      expectFinitePosition(findNode(nodes, id));
    }
  });

  it("scales to a multi-generation tree without producing duplicate or NaN positions", () => {
    const persons = [
      { ...personA, id: "g1-a", display_name: "G1 A", birth_text: "1900" },
      { ...personB, id: "g1-b", display_name: "G1 B", birth_text: "1902" },
      { ...personA, id: "g1-c", display_name: "G1 C", birth_text: "1898" },
      { ...personB, id: "g1-d", display_name: "G1 D", birth_text: "1901" },
      { ...personA, id: "g2-a", display_name: "G2 A", birth_text: "1928" },
      { ...personB, id: "g2-b", display_name: "G2 B", birth_text: "1930" },
      { ...personA, id: "g2-c", display_name: "G2 C", birth_text: "1925" },
      { ...personB, id: "g3-a", display_name: "G3 A", birth_text: "1955" },
      { ...personC, id: "g3-b", display_name: "G3 B", birth_text: "1958" },
    ];
    const { nodes } = buildLayout({
      persons,
      couple_events: [],
      relationships: [
        // G1 couples
        makeRel("r1", "g1-a", "g1-b", "spouse_of"),
        makeRel("r2", "g1-b", "g1-a", "spouse_of"),
        makeRel("r3", "g1-c", "g1-d", "spouse_of"),
        makeRel("r4", "g1-d", "g1-c", "spouse_of"),
        // G2 children of each couple
        makeRel("r5", "g1-a", "g2-a", "parent_of"),
        makeRel("r6", "g1-b", "g2-a", "parent_of"),
        makeRel("r7", "g1-c", "g2-b", "parent_of"),
        makeRel("r8", "g1-d", "g2-b", "parent_of"),
        makeRel("r9", "g1-c", "g2-c", "parent_of"),
        makeRel("r10", "g1-d", "g2-c", "parent_of"),
        // G2 marriage and G3 children
        makeRel("r11", "g2-a", "g2-b", "spouse_of"),
        makeRel("r12", "g2-b", "g2-a", "spouse_of"),
        makeRel("r13", "g2-a", "g3-a", "parent_of"),
        makeRel("r14", "g2-b", "g3-a", "parent_of"),
        makeRel("r15", "g2-a", "g3-b", "parent_of"),
        makeRel("r16", "g2-b", "g3-b", "parent_of"),
      ],
    });

    // No duplicates.
    const ids = nodes.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    // Finite positions everywhere.
    for (const node of nodes) expectFinitePosition(node);
    // Three generations -> three distinct y values for person nodes.
    const yValues = new Set(nodes.filter((n) => n.type === "person").map((n) => n.position.y));
    expect(yValues.size).toBe(3);
    // Younger sibling sits to the right of older sibling.
    expect(findNode(nodes, "g3-a").position.x).toBeLessThan(findNode(nodes, "g3-b").position.x);
  });

  it("swaps spouse positions so each spouse sits on the same side as their parents", () => {
    // Two parent couples with deliberately inverted birth-year sort: the
    // younger couple (Elaine + William, 1950) parents the LEFT child by id,
    // the older couple (Carol + Irwin, 1940) parents the RIGHT child by id.
    // Without alignment the parent edges have to cross. With alignment the
    // child whose parents are on the LEFT ends up on the LEFT.
    const carol = {
      ...personA,
      id: "p-carol",
      display_name: "Carol",
      birth_text: "1940",
    };
    const irwin = {
      ...personB,
      id: "p-irwin",
      display_name: "Irwin",
      birth_text: "1940",
    };
    const elaine = {
      ...personA,
      id: "p-elaine",
      display_name: "Elaine",
      birth_text: "1950",
    };
    const william = {
      ...personB,
      id: "p-william",
      display_name: "William",
      birth_text: "1950",
    };
    // Use ids that put Rebecca BEFORE Gary in the default sort, so the
    // pre-alignment couple bar would put her on the left even though her
    // parents are on the right.
    const rebecca = {
      ...personA,
      id: "child-a-rebecca",
      display_name: "Rebecca",
      birth_text: "1971",
    };
    const gary = {
      ...personB,
      id: "child-b-gary",
      display_name: "Gary",
      birth_text: "1971",
    };
    const { nodes } = buildLayout({
      persons: [carol, irwin, elaine, william, rebecca, gary],
      couple_events: [],
      relationships: [
        // Carol + Irwin couple
        makeRel("r1", "p-carol", "p-irwin", "spouse_of"),
        makeRel("r2", "p-irwin", "p-carol", "spouse_of"),
        // Elaine + William couple
        makeRel("r3", "p-elaine", "p-william", "spouse_of"),
        makeRel("r4", "p-william", "p-elaine", "spouse_of"),
        // Carol + Irwin -> Gary
        makeRel("r5", "p-carol", "child-b-gary", "parent_of"),
        makeRel("r6", "p-irwin", "child-b-gary", "parent_of"),
        // Elaine + William -> Rebecca
        makeRel("r7", "p-elaine", "child-a-rebecca", "parent_of"),
        makeRel("r8", "p-william", "child-a-rebecca", "parent_of"),
        // Rebecca + Gary couple
        makeRel("r9", "child-a-rebecca", "child-b-gary", "spouse_of"),
        makeRel("r10", "child-b-gary", "child-a-rebecca", "spouse_of"),
      ],
    });

    const carolX = findNode(nodes, "p-carol").position.x;
    const elaineX = findNode(nodes, "p-elaine").position.x;
    expect(carolX).toBeLessThan(elaineX);

    const rebeccaX = findNode(nodes, "child-a-rebecca").position.x;
    const garyX = findNode(nodes, "child-b-gary").position.x;
    // Gary's parents are on the LEFT (Carol + Irwin), so Gary should be on
    // the LEFT in the couple bar after alignment.
    expect(garyX).toBeLessThan(rebeccaX);
  });

  it("leaves spouse order alone when only one spouse has parents in the data", () => {
    // Alice has parents on the chart; Bob is a marrying-in spouse with no
    // recorded parents. The alignment pass has nothing to compare and must
    // not alter the default id-sorted order.
    const motherless = { ...personB, id: "p-bob" };
    const aliceWithParents = { ...personA, id: "p-alice" };
    const aliceMom = {
      ...personA,
      id: "p-mom",
      display_name: "Mom",
    };
    const aliceDad = {
      ...personB,
      id: "p-dad",
      display_name: "Dad",
    };
    const { nodes } = buildLayout({
      persons: [aliceMom, aliceDad, aliceWithParents, motherless],
      couple_events: [],
      relationships: [
        makeRel("r1", "p-mom", "p-dad", "spouse_of"),
        makeRel("r2", "p-dad", "p-mom", "spouse_of"),
        makeRel("r3", "p-mom", "p-alice", "parent_of"),
        makeRel("r4", "p-dad", "p-alice", "parent_of"),
        makeRel("r5", "p-alice", "p-bob", "spouse_of"),
        makeRel("r6", "p-bob", "p-alice", "spouse_of"),
      ],
    });
    const aliceX = findNode(nodes, "p-alice").position.x;
    const bobX = findNode(nodes, "p-bob").position.x;
    // Default sort keeps "p-alice" < "p-bob", so Alice stays on the left.
    expect(aliceX).toBeLessThan(bobX);
  });
});
