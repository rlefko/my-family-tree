/**
 * Family-tree visualization. Fetches the full graph from
 * `/api/v1/relationships`, runs a dagre top-down layout, and renders the
 * result with React Flow. Parent_of edges flow vertically; spouse_of /
 * partner_of / sibling_of are deduped to a single horizontal edge per
 * pair (the symmetric mirror is hidden so we don't draw the same line twice).
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

const NODE_WIDTH = 180;
const NODE_HEIGHT = 64;

type PersonCardProps = NodeProps<{ person: PersonNode }>;

function PersonCard({ data, selected }: PersonCardProps) {
  const { person } = data;
  const sexBadge =
    person.sex === "male" ? "♂" : person.sex === "female" ? "♀" : "?";
  const sexClass =
    person.sex === "male"
      ? "bg-sky-100 text-sky-700"
      : person.sex === "female"
        ? "bg-rose-100 text-rose-700"
        : "bg-zinc-100 text-zinc-600";

  return (
    <div
      className={cn(
        "relative rounded-lg border bg-white px-3 py-2 text-xs shadow-sm",
        selected ? "border-indigo-500 ring-2 ring-indigo-200" : "border-zinc-200",
      )}
      style={{ width: NODE_WIDTH }}
    >
      {/* Top edges connect into this node (children of a parent_of edge); */}
      {/* bottom edges connect out (this person is the subject of a parent_of edge); */}
      {/* left/right are used for spouse_of, partner_of, sibling_of pairs. */}
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
        type="target"
        position={Position.Right}
        className="!h-2 !w-2 !bg-zinc-400"
      />
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium text-zinc-900 leading-tight">{person.display_name}</div>
        <span
          className={cn(
            "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
            sexClass,
          )}
        >
          {sexBadge}
        </span>
      </div>
      <div className="mt-1 text-[11px] text-zinc-500">
        {person.birth_text ? <span>b. {person.birth_text}</span> : null}
        {person.birth_text && (person.death_text || !person.is_living) ? " - " : null}
        {person.death_text ? (
          <span>d. {person.death_text}</span>
        ) : !person.is_living && !person.birth_text ? (
          <span>deceased</span>
        ) : null}
      </div>
    </div>
  );
}

const nodeTypes = { person: PersonCard };

function dedupSymmetric(rels: RelationshipRow[]): RelationshipRow[] {
  // For symmetric edges (spouse_of, partner_of, sibling_of) the backend stores
  // both directions; render only one so the edge isn't drawn twice.
  const seen = new Set<string>();
  const symmetric = new Set(["spouse_of", "partner_of", "sibling_of"]);
  const out: RelationshipRow[] = [];
  for (const r of rels) {
    if (symmetric.has(r.type)) {
      const ids = [r.subject_id, r.object_id];
      ids.sort();
      const key = ids.join("|") + ":" + r.type;
      if (seen.has(key)) continue;
      seen.add(key);
    }
    out.push(r);
  }
  return out;
}

function layoutGraph(graph: TreeGraph): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const p of graph.persons) {
    g.setNode(p.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  const rels = dedupSymmetric(graph.relationships);
  for (const r of rels) {
    if (r.type === "parent_of") {
      g.setEdge(r.subject_id, r.object_id);
    }
  }

  dagre.layout(g);

  const nodes: Node[] = graph.persons.map((p) => {
    const layout = g.node(p.id);
    return {
      id: p.id,
      type: "person",
      position: layout
        ? { x: layout.x - NODE_WIDTH / 2, y: layout.y - NODE_HEIGHT / 2 }
        : { x: 0, y: 0 },
      data: { person: p },
    };
  });

  const edges: Edge[] = rels.map((r) => {
    const isParent = r.type === "parent_of";
    const isSpousal = r.type === "spouse_of" || r.type === "partner_of";
    return {
      id: r.id,
      source: r.subject_id,
      target: r.object_id,
      type: isParent ? "smoothstep" : "straight",
      animated: false,
      label: r.type.replaceAll("_", " "),
      labelStyle: { fontSize: 10, fill: "#71717a" },
      style: {
        stroke: isParent ? "#6366f1" : isSpousal ? "#ec4899" : "#a1a1aa",
        strokeWidth: 1.4,
        strokeDasharray: r.type === "sibling_of" ? "4 3" : undefined,
      },
      markerEnd: isParent
        ? { type: MarkerType.ArrowClosed, color: "#6366f1" }
        : undefined,
    };
  });

  return { nodes, edges };
}

export function FamilyTreeGraph({ graph }: { graph: TreeGraph }) {
  const { nodes, edges } = useMemo(() => layoutGraph(graph), [graph]);

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
