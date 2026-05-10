/**
 * Family-tree layered layout.
 *
 * Produces { nodes, edges } for ReactFlow given a TreeGraph. The algorithm is
 * tailored to genealogy and runs in six pure phases:
 *
 *   1. Index relationships into parents-by-child, child-by-parent, and a
 *      deduped couples map (explicit spouse_of / partner_of plus unions
 *      inferred from any pair that shares a child).
 *   2. Assign each person a generation via longest-path top-down relaxation,
 *      lifting the shallower spouse so couples sit on the same row.
 *   3. Build a forest of FamilyUnits. Each person belongs to exactly one
 *      unit, which is either a couple (their primary union, picked by
 *      most-children then earliest marriage then sorted union id) or a solo
 *      person. A unit's children are the units of the persons it parented.
 *   4. Within each unit's child list, sort by parsed birth year then by
 *      display name so siblings appear oldest-left.
 *   5. Walk the unit forest with a Reingold-Tilford-flavored two-pass:
 *      post-order to compute each subtree's width, then pre-order to lay
 *      down x positions with the unit's bar centered over its children.
 *      y comes purely from generation.
 *   6. Emit person nodes, union nodes, couple half-edges, and parent edges.
 *      Each union heart already sits between its spouses from phase 5, so
 *      the couple half-edges are short straight lines.
 *
 * Notes on edge cases:
 *   - Sibling clusters with no asserted parents stay clustered via the
 *     existing sibling_of union-find pass (`inferSiblingParents`); they
 *     surface as solo or couple roots at whatever generation longest-path
 *     produced for them.
 *   - A person with multiple unions only owns one (their primary). The
 *     other union still renders as a heart between two persons, but those
 *     persons may not be adjacent in their generation row. This is an
 *     accepted v1 tradeoff for re-marriages.
 *   - Cycles in parent_of edges (data error) are bounded by an iteration
 *     cap during generation relaxation; we don't crash, the layout just
 *     pins to whatever generation was last assigned.
 */

import { MarkerType, type Edge, type Node } from "reactflow";

import type {
  CoupleEvent,
  PersonNode,
  RelationshipRow,
  TreeGraph,
} from "@/api/endpoints/relationships";

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 84;
export const UNION_WIDTH = 30;
export const UNION_HEIGHT = 30;
export const NODESEP = 36;
const RANKSEP = 80;
const ROOT_GAP = NODESEP * 3;

const COUPLE_TYPES = new Set(["spouse_of", "partner_of"]);
const SIBLING_TYPE = "sibling_of";

type Union = { id: string; a: string; b: string };

type FamilyUnit = {
  id: string;
  generation: number;
  spouses: string[];
  unionId?: string;
  primaryParentUnitId?: string;
  childUnitIds: string[];
};

type Point = { x: number; y: number };

type LayoutOpts = {
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

function couplesKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function makeUnion(a: string, b: string): Union {
  const [first, second] = a < b ? [a, b] : [b, a];
  return { id: `union:${first}|${second}`, a: first, b: second };
}

function collectCouples(rels: RelationshipRow[]): Map<string, Union> {
  const couples = new Map<string, Union>();
  for (const r of rels) {
    if (!COUPLE_TYPES.has(r.type)) continue;
    const key = couplesKey(r.subject_id, r.object_id);
    if (couples.has(key)) continue;
    couples.set(key, makeUnion(r.subject_id, r.object_id));
  }
  return couples;
}

function collectParentsByChild(rels: RelationshipRow[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const r of rels) {
    if (r.type !== "parent_of") continue;
    const list = out.get(r.object_id) ?? [];
    if (!list.includes(r.subject_id)) list.push(r.subject_id);
    out.set(r.object_id, list);
  }
  return out;
}

/**
 * Walk sibling_of relationships and propagate parent_of edges across each
 * sibling cluster. If A is a sibling of B and A has parents X, Y, then we
 * treat B as also having parents X, Y for layout purposes. This keeps
 * siblings on the same generation instead of leaving the parentless ones
 * floating at the top of the chart.
 */
function inferSiblingParents(
  parents: Map<string, string[]>,
  rels: RelationshipRow[],
): Map<string, string[]> {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let cur = x;
    while ((parent.get(cur) ?? cur) !== cur) {
      const p = parent.get(cur) ?? cur;
      parent.set(cur, parent.get(p) ?? p);
      cur = parent.get(cur) ?? cur;
    }
    return cur;
  };
  const link = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };

  for (const r of rels) {
    if (r.type !== SIBLING_TYPE) continue;
    if (!parent.has(r.subject_id)) parent.set(r.subject_id, r.subject_id);
    if (!parent.has(r.object_id)) parent.set(r.object_id, r.object_id);
    link(r.subject_id, r.object_id);
  }

  if (parent.size === 0) return parents;

  const clusterParents = new Map<string, Set<string>>();
  for (const member of parent.keys()) {
    const root = find(member);
    const set = clusterParents.get(root) ?? new Set();
    for (const p of parents.get(member) ?? []) set.add(p);
    clusterParents.set(root, set);
  }

  const inferred = new Map<string, string[]>(parents);
  for (const member of parent.keys()) {
    const root = find(member);
    const cluster = clusterParents.get(root);
    if (!cluster || cluster.size === 0) continue;
    const have = new Set(inferred.get(member) ?? []);
    for (const p of cluster) have.add(p);
    if (have.size > 0) inferred.set(member, [...have]);
  }
  return inferred;
}

/**
 * Augment the couples map with implicit unions inferred from shared children.
 * If A and B both have a parent_of edge to the same C, we treat (A, B) as a
 * couple for layout (joined by a heart, with C's edge coming down from the
 * joiner) even when no explicit spouse_of / partner_of edge exists. Keeps
 * the chart visually cohesive when only parent edges were recorded.
 */
function inferCouplesFromSharedChildren(
  couples: Map<string, Union>,
  parents: Map<string, string[]>,
): Map<string, Union> {
  const out = new Map(couples);
  for (const [, parentList] of parents) {
    if (parentList.length < 2) continue;
    for (let i = 0; i < parentList.length; i++) {
      for (let j = i + 1; j < parentList.length; j++) {
        const a = parentList[i];
        const b = parentList[j];
        const key = couplesKey(a, b);
        if (out.has(key)) continue;
        out.set(key, makeUnion(a, b));
      }
    }
  }
  return out;
}

const YEAR_REGEX = /\b(1[0-9]{3}|2[0-9]{3})\b/;

/**
 * Pull a 4-digit year out of free-form text (a birth_text or marriage date).
 * Returns null when no year is detectable.
 */
function parseYear(text: string | null | undefined): number | null {
  if (!text) return null;
  const m = text.match(YEAR_REGEX);
  return m ? Number.parseInt(m[1], 10) : null;
}

function parseBirthYear(person: PersonNode): number | null {
  return parseYear(person.birth_text);
}

/**
 * Year-then-name comparator for sibling and root ordering. Persons with no
 * parsable birth year sink below dated persons but stay clustered
 * alphabetically.
 */
function compareSiblingPersons(a: PersonNode | undefined, b: PersonNode | undefined): number {
  const ya = a ? parseBirthYear(a) : null;
  const yb = b ? parseBirthYear(b) : null;
  if (ya !== null && yb !== null && ya !== yb) return ya - yb;
  if (ya !== null && yb === null) return -1;
  if (ya === null && yb !== null) return 1;
  return (a?.display_name ?? "").localeCompare(b?.display_name ?? "");
}

/**
 * Assign each person a 0-based generation. Roots (no parents) start at 0;
 * descendants drop by one rank per parent_of hop, taking the longest path
 * so cousins-of-cousins still align. After each relaxation, lift the
 * shallower member of every couple so spouses share a row.
 */
function assignGenerations(
  persons: PersonNode[],
  parents: Map<string, string[]>,
  couples: Map<string, Union>,
): Map<string, number> {
  const gen = new Map<string, number>();
  for (const p of persons) gen.set(p.id, 0);

  const cap = persons.length * 4 + 8;
  let iter = 0;
  let changed = true;
  while (changed && iter++ < cap) {
    changed = false;
    for (const p of persons) {
      const list = parents.get(p.id) ?? [];
      let target = gen.get(p.id) ?? 0;
      for (const parentId of list) {
        const candidate = (gen.get(parentId) ?? 0) + 1;
        if (candidate > target) target = candidate;
      }
      if (target !== (gen.get(p.id) ?? 0)) {
        gen.set(p.id, target);
        changed = true;
      }
    }
    for (const u of couples.values()) {
      const ga = gen.get(u.a) ?? 0;
      const gb = gen.get(u.b) ?? 0;
      if (ga === gb) continue;
      const target = Math.max(ga, gb);
      if ((gen.get(u.a) ?? 0) !== target) {
        gen.set(u.a, target);
        changed = true;
      }
      if ((gen.get(u.b) ?? 0) !== target) {
        gen.set(u.b, target);
        changed = true;
      }
    }
  }
  return gen;
}

/**
 * For each person who appears in at least one union, pick the union we'll
 * treat as their structural home: the one with the most shared children,
 * tiebroken by earliest marriage date in `coupleEventByPair`, tiebroken by
 * sorted union id. Returns personId -> unionId.
 */
function pickPrimaryUnions(
  couples: Map<string, Union>,
  parents: Map<string, string[]>,
  coupleEventByPair: Map<string, { date?: string | null; place?: string | null; type: string }>,
): Map<string, string> {
  const childrenOfUnion = new Map<string, number>();
  const yearOfUnion = new Map<string, number | null>();
  const unionsOf = new Map<string, string[]>();

  for (const u of couples.values()) {
    childrenOfUnion.set(u.id, 0);
    const ev = coupleEventByPair.get(`${couplesKey(u.a, u.b)}:marriage`);
    yearOfUnion.set(u.id, parseYear(ev?.date));
    for (const personId of [u.a, u.b]) {
      const list = unionsOf.get(personId) ?? [];
      list.push(u.id);
      unionsOf.set(personId, list);
    }
  }

  for (const [, parentList] of parents) {
    if (parentList.length < 2) continue;
    for (let i = 0; i < parentList.length; i++) {
      for (let j = i + 1; j < parentList.length; j++) {
        const u = couples.get(couplesKey(parentList[i], parentList[j]));
        if (!u) continue;
        childrenOfUnion.set(u.id, (childrenOfUnion.get(u.id) ?? 0) + 1);
      }
    }
  }

  const primary = new Map<string, string>();
  for (const [personId, unionIds] of unionsOf) {
    let best = unionIds[0];
    for (const candidate of unionIds) {
      if (candidate === best) continue;
      const cChildren = childrenOfUnion.get(candidate) ?? 0;
      const bChildren = childrenOfUnion.get(best) ?? 0;
      if (cChildren !== bChildren) {
        if (cChildren > bChildren) best = candidate;
        continue;
      }
      const cYear = yearOfUnion.get(candidate) ?? null;
      const bYear = yearOfUnion.get(best) ?? null;
      if (cYear !== bYear) {
        if (cYear !== null && (bYear === null || cYear < bYear)) best = candidate;
        continue;
      }
      if (candidate < best) best = candidate;
    }
    primary.set(personId, best);
  }
  return primary;
}

/**
 * Build the FamilyUnit forest. Each person ends up in exactly one unit:
 * a couple unit when the union is primary for both spouses (no contention),
 * or a solo unit otherwise. Re-marriage unions where only one spouse claims
 * this union as primary do not get a couple unit; their heart is dropped at
 * the midpoint between the two solo cards by `placeOrphanUnions`.
 */
function buildFamilyUnits(
  persons: PersonNode[],
  parents: Map<string, string[]>,
  couples: Map<string, Union>,
  generation: Map<string, number>,
  coupleEventByPair: Map<string, { date?: string | null; place?: string | null; type: string }>,
): {
  units: Map<string, FamilyUnit>;
  unitOfPerson: Map<string, string>;
  parentUnitOfPerson: Map<string, string>;
} {
  const primary = pickPrimaryUnions(couples, parents, coupleEventByPair);
  const units = new Map<string, FamilyUnit>();
  const unitOfPerson = new Map<string, string>();
  const parentUnitOfPerson = new Map<string, string>();

  for (const u of couples.values()) {
    const isPrimaryA = primary.get(u.a) === u.id;
    const isPrimaryB = primary.get(u.b) === u.id;
    if (!(isPrimaryA && isPrimaryB)) continue;

    const unitId = `unit:${u.id}`;
    const ga = generation.get(u.a) ?? 0;
    const gb = generation.get(u.b) ?? 0;
    units.set(unitId, {
      id: unitId,
      generation: Math.max(ga, gb),
      spouses: [u.a, u.b],
      unionId: u.id,
      childUnitIds: [],
    });
    unitOfPerson.set(u.a, unitId);
    unitOfPerson.set(u.b, unitId);
  }

  for (const p of persons) {
    if (unitOfPerson.has(p.id)) continue;
    const unitId = `unit:solo:${p.id}`;
    units.set(unitId, {
      id: unitId,
      generation: generation.get(p.id) ?? 0,
      spouses: [p.id],
      childUnitIds: [],
    });
    unitOfPerson.set(p.id, unitId);
  }

  // Link each child unit to one parent unit so the unit forest is a tree.
  // Choose the parent whose unit is the deepest (longest lineage), tiebroken
  // on sorted unit id, so cousin-marriages don't re-root one branch under
  // the other. Only the unit that "owns" the child does the linking; a
  // couple unit is owned by both spouses, so we attach via whichever spouse
  // appears first in the unit (canonical). We also record the chosen parent
  // unit per person so the spouse-alignment pass can compare two spouses'
  // ancestries even when only one of them owns the upward link.
  const claimed = new Set<string>();
  for (const [child, parentList] of parents) {
    const childUnitId = unitOfPerson.get(child);
    if (!childUnitId) continue;
    const childUnit = units.get(childUnitId);
    if (!childUnit) continue;

    let chosen: string | undefined;
    let chosenGen = -Infinity;
    for (const parentId of parentList) {
      const pUnitId = unitOfPerson.get(parentId);
      if (!pUnitId) continue;
      if (pUnitId === childUnitId) continue;
      const pUnit = units.get(pUnitId);
      if (!pUnit) continue;
      const g = pUnit.generation;
      if (g > chosenGen || (g === chosenGen && (chosen === undefined || pUnitId < chosen))) {
        chosen = pUnitId;
        chosenGen = g;
      }
    }
    if (!chosen) continue;
    parentUnitOfPerson.set(child, chosen);
    if (claimed.has(childUnitId)) continue;
    childUnit.primaryParentUnitId = chosen;
    const parentUnit = units.get(chosen);
    if (parentUnit && !parentUnit.childUnitIds.includes(childUnitId)) {
      parentUnit.childUnitIds.push(childUnitId);
    }
    claimed.add(childUnitId);
  }

  return { units, unitOfPerson, parentUnitOfPerson };
}

function orderSiblings(units: Map<string, FamilyUnit>, personById: Map<string, PersonNode>): void {
  for (const unit of units.values()) {
    unit.childUnitIds.sort((a, b) => {
      const ua = units.get(a);
      const ub = units.get(b);
      if (!ua || !ub) return 0;
      return compareSiblingPersons(personById.get(ua.spouses[0]), personById.get(ub.spouses[0]));
    });
  }
}

type LayerGraph = {
  layers: Map<number, FamilyUnit[]>;
  upAdj: Map<string, string[]>;
  downAdj: Map<string, string[]>;
};

const MAX_SWEEPS = 24;

function buildIndexMap(units: FamilyUnit[]): Map<string, number> {
  const out = new Map<string, number>();
  for (let i = 0; i < units.length; i++) out.set(units[i].id, i);
  return out;
}

/**
 * Bucket the units by generation and record every inter-layer adjacency.
 * Tree edges (parent unit -> child unit via `primaryParentUnitId`) are joined
 * by the cross-lineage edges contributed by a couple unit's secondary spouse:
 * if spouse B's parents live in a different unit than the couple's primary
 * parent, we add an extra `(coupleUnit, parentUnitOfB)` adjacency. Those are
 * exactly the edges that turn into long horizontals in the rendered chart,
 * and feeding them to the median sweep is what shortens them.
 */
function buildLayerGraph(
  units: Map<string, FamilyUnit>,
  parentUnitOfPerson: Map<string, string>,
  personById: Map<string, PersonNode>,
): LayerGraph {
  const layers = new Map<number, FamilyUnit[]>();
  for (const unit of units.values()) {
    const list = layers.get(unit.generation) ?? [];
    list.push(unit);
    layers.set(unit.generation, list);
  }
  for (const list of layers.values()) {
    list.sort((a, b) =>
      compareSiblingPersons(personById.get(a.spouses[0]), personById.get(b.spouses[0])),
    );
  }

  const upAdj = new Map<string, string[]>();
  const downAdj = new Map<string, string[]>();
  const addEdge = (parentId: string, childId: string) => {
    if (parentId === childId) return;
    const ups = upAdj.get(childId) ?? [];
    if (!ups.includes(parentId)) ups.push(parentId);
    upAdj.set(childId, ups);
    const downs = downAdj.get(parentId) ?? [];
    if (!downs.includes(childId)) downs.push(childId);
    downAdj.set(parentId, downs);
  };

  for (const unit of units.values()) {
    if (unit.primaryParentUnitId) addEdge(unit.primaryParentUnitId, unit.id);
    for (const spouseId of unit.spouses) {
      const spouseParentUnitId = parentUnitOfPerson.get(spouseId);
      if (!spouseParentUnitId) continue;
      if (spouseParentUnitId === unit.primaryParentUnitId) continue;
      if (spouseParentUnitId === unit.id) continue;
      addEdge(spouseParentUnitId, unit.id);
    }
  }

  return { layers, upAdj, downAdj };
}

/**
 * Count the number of edge crossings between two adjacent layers given the
 * current left-to-right order of each. We pull edges (upper index, lower
 * index) and count inversions on the lower indices via a Fenwick tree, the
 * standard O((n+|E|) log n) algorithm. For small layers an O(|E|^2) sweep
 * would do; the Fenwick version stays fast on the rare wide layer.
 */
function countCrossingsBetween(
  upper: FamilyUnit[],
  lower: FamilyUnit[],
  downAdj: Map<string, string[]>,
): number {
  if (upper.length === 0 || lower.length === 0) return 0;
  const lowerIndex = buildIndexMap(lower);

  const edges: number[] = [];
  for (let u = 0; u < upper.length; u++) {
    const downs = downAdj.get(upper[u].id) ?? [];
    const targets: number[] = [];
    for (const downId of downs) {
      const idx = lowerIndex.get(downId);
      if (idx !== undefined) targets.push(idx);
    }
    targets.sort((a, b) => a - b);
    for (const t of targets) edges.push(t);
  }

  const n = lower.length;
  const tree: number[] = Array.from({ length: n + 1 }, () => 0);
  const bitAdd = (i: number) => {
    for (let x = i + 1; x <= n; x += x & -x) tree[x]++;
  };
  const bitSum = (i: number) => {
    let s = 0;
    for (let x = i + 1; x > 0; x -= x & -x) s += tree[x];
    return s;
  };

  let crossings = 0;
  let inserted = 0;
  for (const t of edges) {
    crossings += inserted - bitSum(t);
    bitAdd(t);
    inserted++;
  }
  return crossings;
}

function totalCrossings(graph: LayerGraph): number {
  const gens = [...graph.layers.keys()];
  gens.sort((a, b) => a - b);
  let total = 0;
  for (let i = 0; i + 1 < gens.length; i++) {
    const upper = graph.layers.get(gens[i]) ?? [];
    const lower = graph.layers.get(gens[i + 1]) ?? [];
    total += countCrossingsBetween(upper, lower, graph.downAdj);
  }
  return total;
}

/**
 * Median heuristic for vertex ordering inside a Sugiyama-style layout.
 * For a unit with k neighbors at indices `i1 < i2 < ... < ik` in the
 * adjacent layer, the median is `i_{floor((k+1)/2)}` for odd k. For even
 * k Gansner et al. recommend a weighted midpoint: `(i_left * (right-mid) +
 * i_right * (mid-left)) / (right-left)` where left, right are the extreme
 * indices and mid is the geometric center. Returns `undefined` when the
 * unit has no neighbors, telling the caller to keep the unit in place.
 */
function medianValue(neighborIndices: number[]): number | undefined {
  if (neighborIndices.length === 0) return undefined;
  const sorted = [...neighborIndices];
  sorted.sort((a, b) => a - b);
  const k = sorted.length;
  if (k === 1) return sorted[0];
  const mid = k >>> 1;
  if (k % 2 === 1) return sorted[mid];
  const left = sorted[mid - 1];
  const right = sorted[mid];
  if (sorted.length === 2) return (left + right) / 2;
  const lo = sorted[0];
  const hi = sorted[sorted.length - 1];
  const leftSpan = left - lo;
  const rightSpan = hi - right;
  if (leftSpan + rightSpan === 0) return (left + right) / 2;
  return (left * rightSpan + right * leftSpan) / (leftSpan + rightSpan);
}

function sortLayerByMedian(
  layer: FamilyUnit[],
  neighborLayer: FamilyUnit[],
  adj: Map<string, string[]>,
  tieBreak: (a: FamilyUnit, b: FamilyUnit) => number,
): FamilyUnit[] {
  if (layer.length <= 1 || neighborLayer.length === 0) return layer;
  const neighborIndex = buildIndexMap(neighborLayer);

  const decorated = layer.map((unit, currentIndex) => {
    const neighborIds = adj.get(unit.id) ?? [];
    const indices: number[] = [];
    for (const id of neighborIds) {
      const idx = neighborIndex.get(id);
      if (idx !== undefined) indices.push(idx);
    }
    return { unit, currentIndex, median: medianValue(indices) };
  });

  decorated.sort((a, b) => {
    const am = a.median;
    const bm = b.median;
    if (am === undefined && bm === undefined) return tieBreak(a.unit, b.unit);
    if (am === undefined) return a.currentIndex - b.currentIndex;
    if (bm === undefined) return a.currentIndex - b.currentIndex;
    if (am !== bm) return am - bm;
    return tieBreak(a.unit, b.unit);
  });
  return decorated.map((d) => d.unit);
}

function cloneLayers(layers: Map<number, FamilyUnit[]>): Map<number, FamilyUnit[]> {
  const out = new Map<number, FamilyUnit[]>();
  for (const [k, v] of layers) out.set(k, [...v]);
  return out;
}

/**
 * Iterative top-down + bottom-up median sweep, the classical Sugiyama
 * crossing-minimization phase. We track the layering with the lowest
 * crossing count seen across all sweeps and return that, which neutralizes
 * the two-cycle oscillation the median heuristic is known for.
 */
function medianSweep(graph: LayerGraph, personById: Map<string, PersonNode>): void {
  const tieBreak = (a: FamilyUnit, b: FamilyUnit) =>
    compareSiblingPersons(personById.get(a.spouses[0]), personById.get(b.spouses[0]));

  const gens = [...graph.layers.keys()];
  gens.sort((a, b) => a - b);
  if (gens.length <= 1) return;

  let bestCrossings = totalCrossings(graph);
  let bestLayers = cloneLayers(graph.layers);

  for (let sweep = 0; sweep < MAX_SWEEPS; sweep++) {
    let changed = false;
    for (let i = 1; i < gens.length; i++) {
      const layer = graph.layers.get(gens[i]) ?? [];
      const above = graph.layers.get(gens[i - 1]) ?? [];
      const reordered = sortLayerByMedian(layer, above, graph.upAdj, tieBreak);
      if (reordered.some((u, idx) => u.id !== layer[idx].id)) {
        graph.layers.set(gens[i], reordered);
        changed = true;
      }
    }
    for (let i = gens.length - 2; i >= 0; i--) {
      const layer = graph.layers.get(gens[i]) ?? [];
      const below = graph.layers.get(gens[i + 1]) ?? [];
      const reordered = sortLayerByMedian(layer, below, graph.downAdj, tieBreak);
      if (reordered.some((u, idx) => u.id !== layer[idx].id)) {
        graph.layers.set(gens[i], reordered);
        changed = true;
      }
    }

    const crossings = totalCrossings(graph);
    if (crossings < bestCrossings) {
      bestCrossings = crossings;
      bestLayers = cloneLayers(graph.layers);
    }
    if (!changed) break;
  }

  for (const [k, v] of bestLayers) graph.layers.set(k, v);
}

/**
 * Push the swept layer ordering back into the unit forest. Each parent's
 * `childUnitIds` is re-sorted by where its children sit in the layer below,
 * and the parentless units of every layer are concatenated into a single
 * canonical root order so coordinate assignment can pack them in the same
 * sequence the sweep settled on.
 */
function applyOrdering(graph: LayerGraph): string[] {
  const gens = [...graph.layers.keys()];
  gens.sort((a, b) => a - b);
  for (let i = 0; i + 1 < gens.length; i++) {
    const lower = graph.layers.get(gens[i + 1]) ?? [];
    const lowerIndex = buildIndexMap(lower);
    const upper = graph.layers.get(gens[i]) ?? [];
    for (const parent of upper) {
      if (parent.childUnitIds.length <= 1) continue;
      parent.childUnitIds.sort((a, b) => {
        const ai = lowerIndex.get(a);
        const bi = lowerIndex.get(b);
        if (ai === undefined && bi === undefined) return 0;
        if (ai === undefined) return 1;
        if (bi === undefined) return -1;
        return ai - bi;
      });
    }
  }

  const rootOrder: string[] = [];
  for (const gen of gens) {
    const layer = graph.layers.get(gen) ?? [];
    for (const unit of layer) {
      if (!unit.primaryParentUnitId) rootOrder.push(unit.id);
    }
  }
  return rootOrder;
}

function unitBarWidth(unit: FamilyUnit): number {
  return unit.spouses.length === 2
    ? NODE_WIDTH + NODESEP + UNION_WIDTH + NODESEP + NODE_WIDTH
    : NODE_WIDTH;
}

/**
 * Two-walk Reingold-Tilford-style placement on the unit forest. Subtree
 * widths in the first walk drive a centered second walk. y is fixed by
 * generation. Returns absolute positions (top-left origin) for every person
 * card and union heart.
 */
function assignCoordinates(
  units: Map<string, FamilyUnit>,
  rootOrder: string[],
): { personPos: Map<string, Point>; unionPos: Map<string, Point> } {
  const subtreeWidth = new Map<string, number>();
  const computeWidth = (unitId: string): number => {
    const cached = subtreeWidth.get(unitId);
    if (cached !== undefined) return cached;
    const unit = units.get(unitId);
    if (!unit) return 0;
    const ownBar = unitBarWidth(unit);
    let childW = 0;
    for (let i = 0; i < unit.childUnitIds.length; i++) {
      childW += computeWidth(unit.childUnitIds[i]);
      if (i > 0) childW += NODESEP;
    }
    const w = Math.max(ownBar, childW);
    subtreeWidth.set(unitId, w);
    return w;
  };

  for (const id of rootOrder) computeWidth(id);

  const personPos = new Map<string, Point>();
  const unionPos = new Map<string, Point>();

  const place = (unitId: string, leftEdge: number) => {
    const unit = units.get(unitId);
    if (!unit) return;
    const w = subtreeWidth.get(unitId) ?? unitBarWidth(unit);
    const ownBar = unitBarWidth(unit);

    let childW = 0;
    for (let i = 0; i < unit.childUnitIds.length; i++) {
      childW += subtreeWidth.get(unit.childUnitIds[i]) ?? 0;
      if (i > 0) childW += NODESEP;
    }
    const childLeft = leftEdge + Math.max(0, (w - childW) / 2);
    let cursor = childLeft;
    for (const childId of unit.childUnitIds) {
      place(childId, cursor);
      cursor += (subtreeWidth.get(childId) ?? 0) + NODESEP;
    }

    const ownLeft = leftEdge + Math.max(0, (w - ownBar) / 2);
    const personY = unit.generation * (NODE_HEIGHT + RANKSEP);
    if (unit.spouses.length === 2 && unit.unionId !== undefined) {
      const aX = ownLeft;
      const unionX = aX + NODE_WIDTH + NODESEP;
      const bX = unionX + UNION_WIDTH + NODESEP;
      personPos.set(unit.spouses[0], { x: aX, y: personY });
      personPos.set(unit.spouses[1], { x: bX, y: personY });
      unionPos.set(unit.unionId, { x: unionX, y: personY + (NODE_HEIGHT - UNION_HEIGHT) / 2 });
    } else {
      personPos.set(unit.spouses[0], { x: ownLeft, y: personY });
    }
  };

  let cursorX = 0;
  for (const id of rootOrder) {
    place(id, cursorX);
    cursorX += (subtreeWidth.get(id) ?? 0) + ROOT_GAP;
  }

  return { personPos, unionPos };
}

/**
 * Position any union nodes that didn't get placed by the unit walk (a
 * non-primary union for someone who's already in a different couple unit).
 * We drop the heart at the midpoint between the two spouses' cards. The
 * couple half-edges then bridge whatever distance separates them.
 */
function placeOrphanUnions(
  couples: Map<string, Union>,
  unionPos: Map<string, Point>,
  personPos: Map<string, Point>,
): void {
  for (const u of couples.values()) {
    if (unionPos.has(u.id)) continue;
    const pa = personPos.get(u.a);
    const pb = personPos.get(u.b);
    if (!pa || !pb) continue;
    const cx = (pa.x + NODE_WIDTH / 2 + pb.x + NODE_WIDTH / 2) / 2 - UNION_WIDTH / 2;
    const cy = (pa.y + pb.y) / 2 + (NODE_HEIGHT - UNION_HEIGHT) / 2;
    unionPos.set(u.id, { x: cx, y: cy });
  }
}

/**
 * X anchor for a parent unit: heart center for couple units, card center
 * for solo units. Returns null when nothing has been placed yet.
 */
function parentAnchorX(
  unit: FamilyUnit | undefined,
  personPos: Map<string, Point>,
  unionPos: Map<string, Point>,
): number | null {
  if (!unit) return null;
  if (unit.unionId !== undefined) {
    const u = unionPos.get(unit.unionId);
    return u ? u.x + UNION_WIDTH / 2 : null;
  }
  const p = personPos.get(unit.spouses[0]);
  return p ? p.x + NODE_WIDTH / 2 : null;
}

/**
 * In a couple unit where both spouses have known parent units, ensure the
 * spouse on the LEFT is the one whose parents sit further LEFT in the
 * generation above. Swapping a couple's spouses moves their card positions
 * but leaves the union heart and any descendants untouched, because heart
 * X is the midpoint of the two card centers and child X depends only on
 * the heart, not on which spouse occupies which side.
 */
function alignSpousesWithParents(
  units: Map<string, FamilyUnit>,
  parentUnitOfPerson: Map<string, string>,
  personPos: Map<string, Point>,
  unionPos: Map<string, Point>,
): void {
  for (const unit of units.values()) {
    if (unit.spouses.length !== 2 || unit.unionId === undefined) continue;
    const [a, b] = unit.spouses;
    const aParentUnitId = parentUnitOfPerson.get(a);
    const bParentUnitId = parentUnitOfPerson.get(b);
    if (!aParentUnitId || !bParentUnitId) continue;
    if (aParentUnitId === bParentUnitId) continue;
    const aPX = parentAnchorX(units.get(aParentUnitId), personPos, unionPos);
    const bPX = parentAnchorX(units.get(bParentUnitId), personPos, unionPos);
    if (aPX === null || bPX === null) continue;
    if (aPX <= bPX) continue;

    const aPos = personPos.get(a);
    const bPos = personPos.get(b);
    if (!aPos || !bPos) continue;
    personPos.set(a, bPos);
    personPos.set(b, aPos);
    unit.spouses = [b, a];
  }
}

function indexCoupleEvents(
  events: CoupleEvent[],
): Map<string, { date?: string | null; place?: string | null; type: string }> {
  const out = new Map<string, { date?: string | null; place?: string | null; type: string }>();
  for (const ev of events) {
    const key = couplesKey(ev.person_a_id, ev.person_b_id);
    out.set(`${key}:${ev.type}`, { date: ev.date_text, place: ev.place_name, type: ev.type });
  }
  return out;
}

function buildChildSources(
  parents: Map<string, string[]>,
  couples: Map<string, Union>,
): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const [child, parentList] of parents) {
    const sources = new Set<string>();
    const consumed = new Set<string>();
    for (let i = 0; i < parentList.length; i++) {
      for (let j = i + 1; j < parentList.length; j++) {
        const a = parentList[i];
        const b = parentList[j];
        const u = couples.get(couplesKey(a, b));
        if (!u) continue;
        sources.add(u.id);
        consumed.add(a);
        consumed.add(b);
      }
    }
    for (const p of parentList) if (!consumed.has(p)) sources.add(p);
    out.set(child, [...sources]);
  }
  return out;
}

export function buildLayout(
  graph: TreeGraph,
  opts: LayoutOpts = {},
): { nodes: Node[]; edges: Edge[] } {
  const explicitCouples = collectCouples(graph.relationships);
  const directParents = collectParentsByChild(graph.relationships);
  const parents = inferSiblingParents(directParents, graph.relationships);
  const couples = inferCouplesFromSharedChildren(explicitCouples, parents);
  const coupleEventByPair = indexCoupleEvents(graph.couple_events ?? []);

  const personById = new Map<string, PersonNode>();
  for (const p of graph.persons) personById.set(p.id, p);

  const generation = assignGenerations(graph.persons, parents, couples);
  const { units, parentUnitOfPerson } = buildFamilyUnits(
    graph.persons,
    parents,
    couples,
    generation,
    coupleEventByPair,
  );
  orderSiblings(units, personById);
  const layerGraph = buildLayerGraph(units, parentUnitOfPerson, personById);
  medianSweep(layerGraph, personById);
  const rootOrder = applyOrdering(layerGraph);
  const { personPos, unionPos } = assignCoordinates(units, rootOrder);
  placeOrphanUnions(couples, unionPos, personPos);
  alignSpousesWithParents(units, parentUnitOfPerson, personPos, unionPos);

  const childSources = buildChildSources(parents, couples);

  const nodes: Node[] = [];
  for (const p of graph.persons) {
    const pos = personPos.get(p.id) ?? { x: 0, y: 0 };
    nodes.push({
      id: p.id,
      type: "person",
      position: pos,
      data: { person: p, onSelect: opts.onSelect },
      selected: opts.selectedId === p.id,
    });
  }
  for (const u of couples.values()) {
    const pos = unionPos.get(u.id);
    if (!pos) continue;
    const pairKey = couplesKey(u.a, u.b);
    const marriage = coupleEventByPair.get(`${pairKey}:marriage`);
    const divorce = coupleEventByPair.get(`${pairKey}:divorce`);
    nodes.push({
      id: u.id,
      type: "union",
      position: pos,
      data: {
        marriageDate: marriage?.date ?? null,
        marriagePlace: marriage?.place ?? null,
        divorceDate: divorce?.date ?? null,
      },
      draggable: false,
      selectable: false,
    });
  }

  const edges: Edge[] = [];
  let i = 0;

  for (const u of couples.values()) {
    if (!unionPos.has(u.id)) continue;
    const unit = units.get(`unit:${u.id}`);
    let left: string;
    let right: string;
    if (unit && unit.spouses.length === 2) {
      left = unit.spouses[0];
      right = unit.spouses[1];
    } else {
      // Orphan union: pick left/right by current X so handles point inward.
      const aPos = personPos.get(u.a);
      const bPos = personPos.get(u.b);
      const aIsLeft = aPos && bPos ? aPos.x <= bPos.x : true;
      left = aIsLeft ? u.a : u.b;
      right = aIsLeft ? u.b : u.a;
    }
    edges.push({
      id: `couple-l-${i++}`,
      source: left,
      target: u.id,
      sourceHandle: "right",
      targetHandle: "left",
      type: "straight",
      style: { stroke: "var(--tree-edge-couple)", strokeWidth: 1.5 },
    });
    edges.push({
      id: `couple-r-${i++}`,
      source: right,
      target: u.id,
      sourceHandle: "left",
      targetHandle: "right",
      type: "straight",
      style: { stroke: "var(--tree-edge-couple)", strokeWidth: 1.5 },
    });
  }

  for (const [child, sources] of childSources) {
    for (const src of sources) {
      edges.push({
        id: `parent-${i++}`,
        source: src,
        target: child,
        type: "smoothstep",
        style: { stroke: "var(--tree-edge-parent)", strokeWidth: 1.5 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "var(--tree-edge-parent)",
          width: 14,
          height: 14,
        },
      });
    }
  }

  return { nodes, edges };
}
