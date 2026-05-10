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

function xOf(nodes: LayoutNode[], id: string): number {
  return findNode(nodes, id).position.x;
}

function makePerson(id: string, name: string, birth: string | null = null) {
  return { ...personA, id, display_name: name, birth_text: birth };
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
    expect(xOf(nodes, "p-old")).toBeLessThan(xOf(nodes, "p-mid"));
    expect(xOf(nodes, "p-mid")).toBeLessThan(xOf(nodes, "p-young"));
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
    expect(xOf(nodes, "p-dated")).toBeLessThan(xOf(nodes, "p-alex"));
    expect(xOf(nodes, "p-alex")).toBeLessThan(xOf(nodes, "p-zoe"));
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
    // younger couple (Donna + Edgar, 1950) parents the LEFT child by id,
    // the older couple (Anne + Ben, 1940) parents the RIGHT child by id.
    // Without alignment the parent edges have to cross. With alignment the
    // child whose parents are on the LEFT ends up on the LEFT.
    const carol = {
      ...personA,
      id: "p-carol",
      display_name: "Anne",
      birth_text: "1940",
    };
    const irwin = {
      ...personB,
      id: "p-irwin",
      display_name: "Ben",
      birth_text: "1940",
    };
    const elaine = {
      ...personA,
      id: "p-elaine",
      display_name: "Donna",
      birth_text: "1950",
    };
    const william = {
      ...personB,
      id: "p-william",
      display_name: "Edgar",
      birth_text: "1950",
    };
    // Use ids that put Fiona BEFORE Greg in the default sort, so the
    // pre-alignment couple bar would put her on the left even though her
    // parents are on the right.
    const rebecca = {
      ...personA,
      id: "child-a-rebecca",
      display_name: "Fiona",
      birth_text: "1971",
    };
    const gary = {
      ...personB,
      id: "child-b-gary",
      display_name: "Greg",
      birth_text: "1971",
    };
    const { nodes } = buildLayout({
      persons: [carol, irwin, elaine, william, rebecca, gary],
      couple_events: [],
      relationships: [
        // Anne + Ben couple
        makeRel("r1", "p-carol", "p-irwin", "spouse_of"),
        makeRel("r2", "p-irwin", "p-carol", "spouse_of"),
        // Donna + Edgar couple
        makeRel("r3", "p-elaine", "p-william", "spouse_of"),
        makeRel("r4", "p-william", "p-elaine", "spouse_of"),
        // Anne + Ben -> Greg
        makeRel("r5", "p-carol", "child-b-gary", "parent_of"),
        makeRel("r6", "p-irwin", "child-b-gary", "parent_of"),
        // Donna + Edgar -> Fiona
        makeRel("r7", "p-elaine", "child-a-rebecca", "parent_of"),
        makeRel("r8", "p-william", "child-a-rebecca", "parent_of"),
        // Fiona + Greg couple
        makeRel("r9", "child-a-rebecca", "child-b-gary", "spouse_of"),
        makeRel("r10", "child-b-gary", "child-a-rebecca", "spouse_of"),
      ],
    });

    const carolX = findNode(nodes, "p-carol").position.x;
    const elaineX = findNode(nodes, "p-elaine").position.x;
    expect(carolX).toBeLessThan(elaineX);

    const rebeccaX = findNode(nodes, "child-a-rebecca").position.x;
    const garyX = findNode(nodes, "child-b-gary").position.x;
    // Greg's parents are on the LEFT (Anne + Ben), so Greg should be on
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

  it("regroups roots so a joined couple's parents end up adjacent", () => {
    // Two unrelated parent couples and one joined-couple child. Without the
    // median sweep, roots are sorted by birth year alone, which can wedge an
    // unrelated root between the two joined-couple parents and force a long
    // cross-lineage edge. With the sweep, the joined-couple parents collapse
    // toward each other and the unrelated root ends up at one end.
    const persons = [
      makePerson("p-strangers-a", "Stranger A", "1925"),
      makePerson("p-strangers-b", "Stranger B", "1928"),
      makePerson("p-momA", "Mom A", "1940"),
      makePerson("p-dadA", "Dad A", "1940"),
      makePerson("p-momB", "Mom B", "1950"),
      makePerson("p-dadB", "Dad B", "1950"),
      makePerson("p-childA", "Joined A", "1972"),
      makePerson("p-childB", "Joined B", "1972"),
    ];
    const { nodes } = buildLayout({
      persons,
      couple_events: [],
      relationships: [
        // Three parent couples: two are joined to a child couple, one isn't.
        makeRel("r1", "p-strangers-a", "p-strangers-b", "spouse_of"),
        makeRel("r2", "p-strangers-b", "p-strangers-a", "spouse_of"),
        makeRel("r3", "p-momA", "p-dadA", "spouse_of"),
        makeRel("r4", "p-dadA", "p-momA", "spouse_of"),
        makeRel("r5", "p-momB", "p-dadB", "spouse_of"),
        makeRel("r6", "p-dadB", "p-momB", "spouse_of"),
        // Joined couple: child of (Mom A + Dad A) marries child of (Mom B + Dad B).
        makeRel("r7", "p-momA", "p-childA", "parent_of"),
        makeRel("r8", "p-dadA", "p-childA", "parent_of"),
        makeRel("r9", "p-momB", "p-childB", "parent_of"),
        makeRel("r10", "p-dadB", "p-childB", "parent_of"),
        makeRel("r11", "p-childA", "p-childB", "spouse_of"),
        makeRel("r12", "p-childB", "p-childA", "spouse_of"),
      ],
    });

    const dadAX = xOf(nodes, "p-dadA");
    const dadBX = xOf(nodes, "p-dadB");
    const strangerAX = xOf(nodes, "p-strangers-a");
    // The unrelated couple (Stranger A + B) must sit outside the
    // (Mom A/Dad A, Mom B/Dad B) span, not wedged between them.
    const joinedSpan: [number, number] = [Math.min(dadAX, dadBX), Math.max(dadAX, dadBX)];
    expect(strangerAX < joinedSpan[0] || strangerAX > joinedSpan[1]).toBe(true);
  });

  it("preserves birth-year sibling order when no cross-lineage pulls exist", () => {
    // The same scenario as the existing birth-year ordering test, but here
    // we explicitly check that the median sweep doesn't shuffle siblings
    // when there's nothing to optimize against.
    const { nodes } = buildLayout({
      persons: [
        makePerson("p-mom", "Mom"),
        makePerson("p-old", "Eldest", "1980"),
        makePerson("p-mid", "Middle", "1984"),
        makePerson("p-yng", "Youngest", "1988"),
      ],
      couple_events: [],
      relationships: [
        makeRel("r1", "p-mom", "p-old", "parent_of"),
        makeRel("r2", "p-mom", "p-mid", "parent_of"),
        makeRel("r3", "p-mom", "p-yng", "parent_of"),
      ],
    });
    expect(xOf(nodes, "p-old")).toBeLessThan(xOf(nodes, "p-mid"));
    expect(xOf(nodes, "p-mid")).toBeLessThan(xOf(nodes, "p-yng"));
  });

  it("converges on a graph with multiple joined couples without crashing", () => {
    // Two joined couples cross each other through their child couples'
    // children. Verify finite positions and no thrown errors.
    const persons = [
      makePerson("a-mom", "a-mom", "1920"),
      makePerson("a-dad", "a-dad", "1920"),
      makePerson("b-mom", "b-mom", "1925"),
      makePerson("b-dad", "b-dad", "1925"),
      makePerson("c-mom", "c-mom", "1928"),
      makePerson("c-dad", "c-dad", "1928"),
      makePerson("a-kid", "a-kid", "1948"),
      makePerson("b-kid", "b-kid", "1948"),
      makePerson("c-kid", "c-kid", "1950"),
      makePerson("d-kid", "d-kid", "1950"),
      makePerson("g1", "g1", "1972"),
      makePerson("g2", "g2", "1974"),
    ];
    const { nodes } = buildLayout({
      persons,
      couple_events: [],
      relationships: [
        makeRel("r1", "a-mom", "a-dad", "spouse_of"),
        makeRel("r2", "a-dad", "a-mom", "spouse_of"),
        makeRel("r3", "b-mom", "b-dad", "spouse_of"),
        makeRel("r4", "b-dad", "b-mom", "spouse_of"),
        makeRel("r5", "c-mom", "c-dad", "spouse_of"),
        makeRel("r6", "c-dad", "c-mom", "spouse_of"),
        makeRel("r7", "a-mom", "a-kid", "parent_of"),
        makeRel("r8", "a-dad", "a-kid", "parent_of"),
        makeRel("r9", "b-mom", "b-kid", "parent_of"),
        makeRel("r10", "b-dad", "b-kid", "parent_of"),
        makeRel("r11", "c-mom", "c-kid", "parent_of"),
        makeRel("r12", "c-dad", "c-kid", "parent_of"),
        makeRel("r13", "c-mom", "d-kid", "parent_of"),
        makeRel("r14", "c-dad", "d-kid", "parent_of"),
        makeRel("r15", "a-kid", "b-kid", "spouse_of"),
        makeRel("r16", "b-kid", "a-kid", "spouse_of"),
        makeRel("r17", "c-kid", "d-kid", "spouse_of"),
        makeRel("r18", "d-kid", "c-kid", "spouse_of"),
        makeRel("r19", "a-kid", "g1", "parent_of"),
        makeRel("r20", "b-kid", "g1", "parent_of"),
        makeRel("r21", "c-kid", "g2", "parent_of"),
        makeRel("r22", "d-kid", "g2", "parent_of"),
      ],
    });
    expect(nodes.length).toBeGreaterThan(0);
    for (const node of nodes) expectFinitePosition(node);
  });

  it("handles a wide sibship without spinning out", () => {
    // 12 siblings under one parent couple: the median sweep must still
    // finish quickly and produce finite positions.
    const persons = [makePerson("wide-mom", "Mom"), makePerson("wide-dad", "Dad")];
    const rels = [
      makeRel("r-spouse-1", "wide-mom", "wide-dad", "spouse_of"),
      makeRel("r-spouse-2", "wide-dad", "wide-mom", "spouse_of"),
    ];
    for (let i = 0; i < 12; i++) {
      const id = `wide-kid-${i}`;
      persons.push(makePerson(id, `Kid ${i}`, `${1970 + i}`));
      rels.push(makeRel(`r-mom-${i}`, "wide-mom", id, "parent_of"));
      rels.push(makeRel(`r-dad-${i}`, "wide-dad", id, "parent_of"));
    }
    const start = Date.now();
    const { nodes } = buildLayout({ persons, couple_events: [], relationships: rels });
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(500);
    for (const node of nodes) expectFinitePosition(node);
  });

  it("centers a joined couple roughly between its two parent unions", () => {
    // Mom A + Dad A and Mom B + Dad B are roots; Joined A + Joined B is the
    // child couple. Without centering the joined couple is parked under one
    // root; with centering it sits near the midpoint of the two parent
    // hearts so the cross-lineage edge is short.
    const persons = [
      makePerson("p-momA", "Mom A", "1940"),
      makePerson("p-dadA", "Dad A", "1940"),
      makePerson("p-momB", "Mom B", "1950"),
      makePerson("p-dadB", "Dad B", "1950"),
      makePerson("child-a", "Joined A", "1972"),
      makePerson("child-b", "Joined B", "1972"),
    ];
    const { nodes } = buildLayout({
      persons,
      couple_events: [],
      relationships: [
        makeRel("r1", "p-momA", "p-dadA", "spouse_of"),
        makeRel("r2", "p-dadA", "p-momA", "spouse_of"),
        makeRel("r3", "p-momB", "p-dadB", "spouse_of"),
        makeRel("r4", "p-dadB", "p-momB", "spouse_of"),
        makeRel("r5", "p-momA", "child-a", "parent_of"),
        makeRel("r6", "p-dadA", "child-a", "parent_of"),
        makeRel("r7", "p-momB", "child-b", "parent_of"),
        makeRel("r8", "p-dadB", "child-b", "parent_of"),
        makeRel("r9", "child-a", "child-b", "spouse_of"),
        makeRel("r10", "child-b", "child-a", "spouse_of"),
      ],
    });

    const aHeart = nodes.find((n) => n.id.startsWith("union:") && n.id.includes("p-dadA"));
    const bHeart = nodes.find((n) => n.id.startsWith("union:") && n.id.includes("p-dadB"));
    const childHeart = nodes.find((n) => n.id.startsWith("union:") && n.id.includes("child-a"));
    expect(aHeart).toBeDefined();
    expect(bHeart).toBeDefined();
    expect(childHeart).toBeDefined();

    const aCenter = (aHeart?.position.x ?? 0) + UNION_WIDTH / 2;
    const bCenter = (bHeart?.position.x ?? 0) + UNION_WIDTH / 2;
    const target = (aCenter + bCenter) / 2;
    const childCenter = (childHeart?.position.x ?? 0) + UNION_WIDTH / 2;
    // After centering, the joined couple's heart should sit within
    // NODE_WIDTH of the midpoint of its parent hearts.
    expect(Math.abs(childCenter - target)).toBeLessThan(NODE_WIDTH);
  });

  it("respects sibling boundaries when centering a joined couple", () => {
    // Mom A + Dad A have THREE children. The middle one is joined to a child
    // of Mom B + Dad B. Centering should not push the joined couple past its
    // siblings' bounds even if the parent unions are far apart.
    const persons = [
      makePerson("p-momA", "Mom A", "1940"),
      makePerson("p-dadA", "Dad A", "1940"),
      makePerson("p-momB", "Mom B", "1950"),
      makePerson("p-dadB", "Dad B", "1950"),
      makePerson("sib-1", "Sibling One", "1970"),
      makePerson("child-a", "Joined A", "1972"),
      makePerson("sib-2", "Sibling Two", "1974"),
      makePerson("child-b", "Joined B", "1972"),
    ];
    const { nodes } = buildLayout({
      persons,
      couple_events: [],
      relationships: [
        makeRel("r1", "p-momA", "p-dadA", "spouse_of"),
        makeRel("r2", "p-dadA", "p-momA", "spouse_of"),
        makeRel("r3", "p-momB", "p-dadB", "spouse_of"),
        makeRel("r4", "p-dadB", "p-momB", "spouse_of"),
        makeRel("r5", "p-momA", "sib-1", "parent_of"),
        makeRel("r6", "p-dadA", "sib-1", "parent_of"),
        makeRel("r7", "p-momA", "child-a", "parent_of"),
        makeRel("r8", "p-dadA", "child-a", "parent_of"),
        makeRel("r9", "p-momA", "sib-2", "parent_of"),
        makeRel("r10", "p-dadA", "sib-2", "parent_of"),
        makeRel("r11", "p-momB", "child-b", "parent_of"),
        makeRel("r12", "p-dadB", "child-b", "parent_of"),
        makeRel("r13", "child-a", "child-b", "spouse_of"),
        makeRel("r14", "child-b", "child-a", "spouse_of"),
      ],
    });

    // Siblings can end up in any order (the swap optimizer is allowed to
    // pull the joined sibling toward Mom B's side), but all three must sit
    // in distinct, non-overlapping x slots — that's the invariant the
    // centering pass's bounds-clipping guarantees.
    const sibs = [xOf(nodes, "sib-1"), xOf(nodes, "child-a"), xOf(nodes, "sib-2")];
    sibs.sort((a, b) => a - b);
    expect(sibs[0] + NODE_WIDTH).toBeLessThanOrEqual(sibs[1]);
    expect(sibs[1] + NODE_WIDTH).toBeLessThanOrEqual(sibs[2]);
  });
});
