/**
 * Family-tree visualization in the ancestry-style layout: spouses are joined
 * by a small union node, children's lines descend from the union, and sibling
 * edges are not rendered (they're implied by shared parents).
 *
 * Layout pipeline:
 *   1. Dedup spouse_of / partner_of pairs into a `unions` map.
 *   2. For each child, find their parents. If two parents share a union, the
 *      child gets one edge from that union; otherwise each parent gets a
 *      direct edge to the child.
 *   3. Insert synthetic union nodes between each spouse pair.
 *   4. Run dagre top-down. Spouses end up at the same row above their union
 *      because both have edges into the union.
 */

import dagre from "@dagrejs/dagre";
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

const NODE_WIDTH = 200;
const NODE_HEIGHT = 70;
const UNION_SIZE = 14;

const SYMMETRIC = new Set(["spouse_of", "partner_of", "sibling_of"]);
const COUPLE_TYPES = new Set(["spouse_of", "partner_of"]);

type PersonCardProps = NodeProps<{ person: PersonNode; onSelect?: (id: string) => void }>;

function PersonCard({ data, selected, id }: PersonCardProps) {
  const { person, onSelect } = data;
  const sexBadge = person.sex === "male" ? "M" : person.sex === "female" ? "F" : "?";
  const sexBg =
    person.sex === "male"
      ? "bg-sky-50 border-sky-200"
      : person.sex === "female"
        ? "bg-rose-50 border-rose-200"
        : "bg-zinc-50 border-zinc-200";
  const sexChip =
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

  return (
    <button
      type="button"
      onClick={() => onSelect?.(id)}
      className={cn(
        "relative flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left text-xs shadow-sm transition-shadow hover:shadow-md",
        sexBg,
        selected ? "ring-2 ring-indigo-500" : "",
      )}
      style={{ width: NODE_WIDTH }}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-zinc-400" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-zinc-400" />
      <Handle
        id="left"
        type="source"
        position={Position.Left}
        className="!h-2 !w-2 !bg-zinc-400"
      />
      <Handle
        id="right"
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !bg-zinc-400"
      />

      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
          sexChip,
        )}
      >
        {initials || "?"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium text-zinc-900">{person.display_name}</div>
        <div className="text-[10px] text-zinc-500">
          {[person.birth_text ? `b. ${person.birth_text}` : null, person.death_text ? `d. ${person.death_text}` : null]
            .filter(Boolean)
            .join(" • ") || (person.is_living ? "living" : "")}
        </div>
      </div>
      <span className={cn("shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold", sexChip)}>
        {sexBadge}
      </span>
    </button>
  );
}

function UnionNode() {
  return (
    <div
      className="relative rounded-full border border-pink-300 bg-pink-100 shadow-sm"
      style={{ width: UNION_SIZE, height: UNION_SIZE }}
      aria-label="union"
      title="union"
    >
      <Handle id="left" type="target" position={Position.Left} className="!h-2 !w-2 !bg-pink-400" />
      <Handle
        id="right"
        type="target"
        position={Position.Right}
        className="!h-2 !w-2 !bg-pink-400"
      />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-pink-400" />
    </div>
  );
}

const nodeTypes = { person: PersonCard, union: UnionNode };

type LayoutOpts = {
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

export function buildLayout(graph: TreeGraph, opts: LayoutOpts = {}): { nodes: Node[]; edges: Edge[] } {
  const personById = new Map(graph.persons.map((p) => [p.id, p] as const));
  const couples = collectCouples(graph.relationships);
  const parentSet = collectParentsByChild(graph.relationships);

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 60, marginx: 20, marginy: 20 });
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  for (const p of graph.persons) {
    dagreGraph.setNode(p.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  // Add union nodes and connect spouses into them.
  const layoutEdges: { source: string; target: string; sourceHandle?: string; targetHandle?: string; couple?: boolean }[] = [];
  for (const [, union] of couples) {
    dagreGraph.setNode(union.id, { width: UNION_SIZE, height: UNION_SIZE });
    dagreGraph.setEdge(union.a, union.id, { weight: 5, minlen: 1 });
    dagreGraph.setEdge(union.b, union.id, { weight: 5, minlen: 1 });
    layoutEdges.push({ source: union.a, target: union.id, sourceHandle: "right", targetHandle: "left", couple: true });
    layoutEdges.push({ source: union.b, target: union.id, sourceHandle: "left", targetHandle: "right", couple: true });
  }

  // For every child, pick the source: union (if both parents share one) or direct parent.
  const childToSources = new Map<string, string[]>();
  for (const [child, parents] of parentSet) {
    const sources = new Set<string>();
    const consumed = new Set<string>();
    for (let i = 0; i < parents.length; i++) {
      for (let j = i + 1; j < parents.length; j++) {
        const a = parents[i];
        const b = parents[j];
        const key = couplesKey(a, b);
        const u = couples.get(key);
        if (u) {
          sources.add(u.id);
          consumed.add(a);
          consumed.add(b);
        }
      }
    }
    for (const p of parents) if (!consumed.has(p)) sources.add(p);
    childToSources.set(child, [...sources]);
  }

  for (const [child, sources] of childToSources) {
    for (const src of sources) {
      dagreGraph.setEdge(src, child, { weight: 1, minlen: 1 });
      layoutEdges.push({ source: src, target: child });
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
  for (const [, union] of couples) {
    const layout = dagreGraph.node(union.id);
    if (!layout) continue;
    nodes.push({
      id: union.id,
      type: "union",
      position: { x: layout.x - UNION_SIZE / 2, y: layout.y - UNION_SIZE / 2 },
      data: {},
      draggable: false,
      selectable: false,
    });
  }

  const edges: Edge[] = [];
  let i = 0;
  for (const e of layoutEdges) {
    const src = personById.get(e.source);
    const tgt = personById.get(e.target);
    if (e.couple) {
      // spouse half-edges into the union (horizontal)
      edges.push({
        id: `couple-${i++}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        type: "straight",
        style: { stroke: "#ec4899", strokeWidth: 2 },
      });
    } else {
      edges.push({
        id: `parent-${i++}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        style: { stroke: "#6366f1", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#6366f1" },
      });
    }
    void src;
    void tgt;
  }

  return { nodes, edges };
}

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

export function FamilyTreeGraph({
  graph,
  onSelect,
  selectedId,
}: {
  graph: TreeGraph;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
}) {
  // Drop sibling_of edges before layout — they're implied by shared parents and
  // would otherwise add visual noise plus mess up the dagre rank assignment.
  const filteredGraph = useMemo<TreeGraph>(
    () => ({
      persons: graph.persons,
      relationships: graph.relationships.filter((r) => !SYMMETRIC.has(r.type) || COUPLE_TYPES.has(r.type)),
    }),
    [graph],
  );
  const { nodes, edges } = useMemo(
    () => buildLayout(filteredGraph, { onSelect, selectedId }),
    [filteredGraph, onSelect, selectedId],
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
        fitViewOptions={{ padding: 0.15 }}
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
