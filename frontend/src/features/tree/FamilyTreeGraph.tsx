/**
 * Family-tree visualization in ancestry style.
 *
 * Layout pipeline:
 *   1. Compute "implied parent" edges from sibling_of relationships, so a
 *      person who is asserted as someone's sibling but has no parent_of
 *      edges of their own still ranks at the same row as their sibling.
 *   2. Build a `unions` map by deduping spouse_of / partner_of pairs.
 *   3. For each child, find their parents. If two parents share a union, the
 *      child gets ONE edge from that union; otherwise each parent edges to
 *      the child directly.
 *   4. Run dagre top-down with parent->child edges only (unions are visual).
 *   5. After layout, place each union node at the midpoint between its
 *      spouses and at the same Y so the edge sits between them like a
 *      wedding bar.
 *
 * Sibling_of edges are NOT drawn — the layout already groups siblings under
 * shared parents, which is how genealogy charts represent siblinghood.
 */

import dagre from "@dagrejs/dagre";
import { Heart } from "lucide-react";
import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  Controls,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";

import "reactflow/dist/style.css";

import type { PersonNode, RelationshipRow, TreeGraph } from "@/api/endpoints/relationships";
import { cn } from "@/lib/utils";

const NODE_WIDTH = 220;
const NODE_HEIGHT = 84;
const UNION_WIDTH = 30;
const UNION_HEIGHT = 30;

const COUPLE_TYPES = new Set(["spouse_of", "partner_of"]);
const SIBLING_TYPE = "sibling_of";

type PersonCardProps = NodeProps<{ person: PersonNode; onSelect?: (id: string) => void }>;

function PersonCard({ data, selected, id }: PersonCardProps) {
  const { person, onSelect } = data;
  const sexBadge = person.sex === "male" ? "M" : person.sex === "female" ? "F" : "?";
  const cardBg =
    person.sex === "male"
      ? "bg-sky-50 border-sky-200"
      : person.sex === "female"
        ? "bg-rose-50 border-rose-200"
        : "bg-zinc-50 border-zinc-200";
  const chip =
    person.sex === "male"
      ? "bg-sky-100 text-sky-700"
      : person.sex === "female"
        ? "bg-rose-100 text-rose-700"
        : "bg-zinc-100 text-zinc-600";
  const initials = person.display_name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
  const dates =
    [person.birth_text ? `b. ${person.birth_text}` : null, person.death_text ? `d. ${person.death_text}` : null]
      .filter(Boolean)
      .join(" • ") || (person.is_living ? "living" : "");

  return (
    <button
      type="button"
      onClick={() => onSelect?.(id)}
      className={cn(
        "relative flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left text-xs shadow-sm transition-shadow hover:shadow-md",
        cardBg,
        selected ? "ring-2 ring-indigo-500" : "",
      )}
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-zinc-400" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-zinc-400" />
      <Handle id="left" type="source" position={Position.Left} className="!h-2 !w-2 !bg-pink-400" />
      <Handle id="right" type="source" position={Position.Right} className="!h-2 !w-2 !bg-pink-400" />

      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
          chip,
        )}
      >
        {initials || "?"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words font-medium leading-tight text-zinc-900">
          {person.display_name}
        </div>
        {dates ? <div className="mt-0.5 text-[10px] text-zinc-500">{dates}</div> : null}
      </div>
      <span className={cn("shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold", chip)}>
        {sexBadge}
      </span>
    </button>
  );
}

function UnionNode() {
  return (
    <div
      className="relative flex items-center justify-center rounded-full border-2 border-pink-300 bg-white shadow-sm"
      style={{ width: UNION_WIDTH, height: UNION_HEIGHT }}
      aria-label="union"
      title="marriage / partnership"
    >
      <Heart className="h-3.5 w-3.5 text-pink-500" />
      <Handle id="left" type="target" position={Position.Left} className="!h-2 !w-2 !bg-pink-400" />
      <Handle id="right" type="target" position={Position.Right} className="!h-2 !w-2 !bg-pink-400" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-pink-400" />
    </div>
  );
}

const nodeTypes = { person: PersonCard, union: UnionNode };

type Union = { id: string; a: string; b: string };

function couplesKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function collectCouples(rels: RelationshipRow[]): Map<string, Union> {
  const couples = new Map<string, Union>();
  for (const r of rels) {
    if (!COUPLE_TYPES.has(r.type)) continue;
    const key = couplesKey(r.subject_id, r.object_id);
    if (couples.has(key)) continue;
    const ids = [r.subject_id, r.object_id];
    ids.sort();
    couples.set(key, { id: `union:${key}`, a: ids[0], b: ids[1] });
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
 * siblings on the same dagre rank instead of leaving the parentless ones
 * at the top of the chart.
 */
function inferSiblingParents(parents: Map<string, string[]>, rels: RelationshipRow[]): Map<string, string[]> {
  // Union-find over sibling_of relationships.
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

  // Cluster -> set of parents present in any cluster member.
  const clusterParents = new Map<string, Set<string>>();
  for (const member of parent.keys()) {
    const root = find(member);
    const set = clusterParents.get(root) ?? new Set();
    for (const p of parents.get(member) ?? []) set.add(p);
    clusterParents.set(root, set);
  }

  // Apply cluster parents back to each member.
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

type LayoutOpts = {
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

export function buildLayout(graph: TreeGraph, opts: LayoutOpts = {}): { nodes: Node[]; edges: Edge[] } {
  const couples = collectCouples(graph.relationships);
  const directParents = collectParentsByChild(graph.relationships);
  const parents = inferSiblingParents(directParents, graph.relationships);

  // Build child -> [source-id]: either union-id (when both parents share one)
  // or individual parent ids.
  const childSources = new Map<string, string[]>();
  for (const [child, parentList] of parents) {
    const sources = new Set<string>();
    const consumed = new Set<string>();
    for (let i = 0; i < parentList.length; i++) {
      for (let j = i + 1; j < parentList.length; j++) {
        const a = parentList[i];
        const b = parentList[j];
        const u = couples.get(couplesKey(a, b));
        if (u) {
          sources.add(u.id);
          consumed.add(a);
          consumed.add(b);
        }
      }
    }
    for (const p of parentList) if (!consumed.has(p)) sources.add(p);
    childSources.set(child, [...sources]);
  }

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setGraph({ rankdir: "TB", nodesep: 36, ranksep: 80, marginx: 30, marginy: 30 });
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  for (const p of graph.persons) {
    dagreGraph.setNode(p.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const [, u] of couples) {
    // Don't add union as a dagre node; we position it manually after layout.
    void u;
  }
  for (const [child, sources] of childSources) {
    for (const src of sources) {
      // Couple edges: one composite edge from each spouse so dagre keeps them
      // on the same row above the child. We render the visual union later.
      if (src.startsWith("union:")) {
        const u = couples.get(src.slice("union:".length));
        if (u) {
          dagreGraph.setEdge(u.a, child, { weight: 2, minlen: 1 });
          dagreGraph.setEdge(u.b, child, { weight: 2, minlen: 1 });
        }
      } else {
        dagreGraph.setEdge(src, child, { weight: 2, minlen: 1 });
      }
    }
  }

  dagre.layout(dagreGraph);

  const nodes: Node[] = [];
  for (const p of graph.persons) {
    const layout = dagreGraph.node(p.id);
    nodes.push({
      id: p.id,
      type: "person",
      position: layout
        ? { x: layout.x - NODE_WIDTH / 2, y: layout.y - NODE_HEIGHT / 2 }
        : { x: 0, y: 0 },
      data: { person: p, onSelect: opts.onSelect },
      selected: opts.selectedId === p.id,
    });
  }

  // Position each union halfway between its two spouses, vertically aligned
  // with their center.
  for (const [, u] of couples) {
    const a = dagreGraph.node(u.a);
    const b = dagreGraph.node(u.b);
    if (!a || !b) continue;
    const x = (a.x + b.x) / 2;
    const y = (a.y + b.y) / 2;
    nodes.push({
      id: u.id,
      type: "union",
      position: { x: x - UNION_WIDTH / 2, y: y - UNION_HEIGHT / 2 },
      data: {},
      draggable: false,
      selectable: false,
    });
  }

  const edges: Edge[] = [];
  let i = 0;

  // Spouse half-edges into the union (visual only — short horizontal lines).
  for (const [, u] of couples) {
    edges.push({
      id: `couple-l-${i++}`,
      source: u.a,
      target: u.id,
      sourceHandle: "right",
      targetHandle: "left",
      type: "straight",
      style: { stroke: "#ec4899", strokeWidth: 1.5 },
    });
    edges.push({
      id: `couple-r-${i++}`,
      source: u.b,
      target: u.id,
      sourceHandle: "left",
      targetHandle: "right",
      type: "straight",
      style: { stroke: "#ec4899", strokeWidth: 1.5 },
    });
  }

  // Parent edges to children.
  for (const [child, sources] of childSources) {
    for (const src of sources) {
      edges.push({
        id: `parent-${i++}`,
        source: src,
        target: child,
        type: "smoothstep",
        style: { stroke: "#6366f1", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#6366f1", width: 14, height: 14 },
      });
    }
  }

  return { nodes, edges };
}

export function FamilyTreeGraph({
  graph,
  onSelect,
  selectedId,
}: {
  graph: TreeGraph;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
}) {
  // Drop sibling_of from the visual layer; we already used it to enrich the
  // parent map in buildLayout so siblings end up at the same row.
  const filteredGraph = useMemo<TreeGraph>(
    () => ({
      persons: graph.persons,
      relationships: graph.relationships.filter((r) => r.type !== SIBLING_TYPE),
    }),
    [graph],
  );
  const { nodes, edges } = useMemo(
    () => buildLayout({ persons: filteredGraph.persons, relationships: graph.relationships }, { onSelect, selectedId }),
    [graph.relationships, filteredGraph.persons, onSelect, selectedId],
  );

  if (graph.persons.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-10 text-center text-sm text-zinc-500">
        No people in the tree yet. Use the Chat to add some.
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        connectionLineType={ConnectionLineType.SmoothStep}
        proOptions={{ hideAttribution: true }}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <Controls position="bottom-right" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
