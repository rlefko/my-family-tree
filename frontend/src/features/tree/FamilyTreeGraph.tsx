/**
 * Family-tree visualization in ancestry style.
 *
 * Heavy lifting lives in `./layout`: a custom layered layout that walks the
 * unit forest (couples + solo persons) to produce ReactFlow nodes and edges
 * with spouses adjacent, the union heart between them, siblings ordered
 * oldest-left, and parent edges sourced from the union when both parents
 * share one. This file is the React surface only.
 */

import { Heart } from "lucide-react";
import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  Controls,
  Handle,
  Position,
  type NodeProps,
} from "reactflow";

import "reactflow/dist/style.css";

import type { PersonNode, TreeGraph } from "@/api/endpoints/relationships";
import { personInitials } from "@/lib/names";
import { cn } from "@/lib/utils";

import { buildLayout, NODE_HEIGHT, NODE_WIDTH, UNION_HEIGHT, UNION_WIDTH } from "./layout";

const SIBLING_TYPE = "sibling_of";

type PersonCardProps = NodeProps<{ person: PersonNode; onSelect?: (id: string) => void }>;

function SexBadge({ sex, className }: { sex: PersonNode["sex"]; className?: string }) {
  // Unicode gender glyphs read clean at small sizes and don't depend on a
  // specific lucide-react version (Mars/Venus icons aren't in 0.468.x).
  const glyph = sex === "male" ? "♂" : sex === "female" ? "♀" : "?";
  const tone =
    sex === "male"
      ? "text-sky-700 dark:text-sky-300"
      : sex === "female"
        ? "text-rose-700 dark:text-rose-300"
        : "text-muted-foreground";
  return (
    <span
      aria-label={`sex: ${sex}`}
      className={cn("text-sm font-bold leading-none", tone, className)}
    >
      {glyph}
    </span>
  );
}

function PersonCard({ data, selected, id }: PersonCardProps) {
  const { person, onSelect } = data;
  const cardBg =
    person.sex === "male"
      ? "bg-sky-50 border-sky-200 dark:bg-sky-950/40 dark:border-sky-900"
      : person.sex === "female"
        ? "bg-rose-50 border-rose-200 dark:bg-rose-950/40 dark:border-rose-900"
        : "bg-card border-border";
  const chipBg =
    person.sex === "male"
      ? "bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-200"
      : person.sex === "female"
        ? "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-200"
        : "bg-muted text-muted-foreground";
  const initials = personInitials(person);
  const dates =
    [
      person.birth_text ? `b. ${person.birth_text}` : null,
      person.death_text ? `d. ${person.death_text}` : null,
    ]
      .filter(Boolean)
      .join(" • ") || (person.is_living ? "living" : "");

  return (
    <button
      type="button"
      onClick={() => onSelect?.(id)}
      className={cn(
        "relative flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left text-xs shadow-sm transition-shadow hover:shadow-md",
        cardBg,
        selected ? "ring-2 ring-ring" : "",
      )}
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-muted-foreground" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-muted-foreground" />
      <Handle id="left" type="source" position={Position.Left} className="!h-2 !w-2 !bg-pink-400" />
      <Handle
        id="right"
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !bg-pink-400"
      />

      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
          chipBg,
        )}
      >
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="break-words font-medium leading-tight text-foreground">
          {person.display_name}
        </div>
        {dates ? <div className="mt-0.5 text-[10px] text-muted-foreground">{dates}</div> : null}
      </div>
      <span
        className={cn("inline-flex shrink-0 items-center justify-center rounded-full p-1", chipBg)}
      >
        <SexBadge sex={person.sex} />
      </span>
    </button>
  );
}

type UnionNodeData = {
  marriageDate?: string | null;
  marriagePlace?: string | null;
  divorceDate?: string | null;
};

function UnionNode({ data }: NodeProps<UnionNodeData>) {
  const tip =
    [
      data.marriageDate ? `Married: ${data.marriageDate}` : null,
      data.marriagePlace ? `Place: ${data.marriagePlace}` : null,
      data.divorceDate ? `Divorced: ${data.divorceDate}` : null,
    ]
      .filter(Boolean)
      .join("\n") || "Marriage / partnership";
  return (
    <div className="relative">
      <div
        className="relative flex items-center justify-center rounded-full border-2 border-pink-300 bg-card shadow-sm dark:border-pink-700"
        style={{ width: UNION_WIDTH, height: UNION_HEIGHT }}
        aria-label="union"
        title={tip}
      >
        <Heart className="h-3.5 w-3.5 text-pink-500 dark:text-pink-400" />
        <Handle
          id="left"
          type="target"
          position={Position.Left}
          className="!h-2 !w-2 !bg-pink-400"
        />
        <Handle
          id="right"
          type="target"
          position={Position.Right}
          className="!h-2 !w-2 !bg-pink-400"
        />
        <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-pink-400" />
      </div>
      {data.marriageDate || data.marriagePlace ? (
        <div className="pointer-events-none absolute left-1/2 top-full mt-1 -translate-x-1/2 whitespace-nowrap rounded bg-card/95 px-1.5 py-0.5 text-[9px] font-medium text-pink-700 shadow-sm ring-1 ring-pink-200 dark:text-pink-300 dark:ring-pink-800">
          {data.marriageDate ?? ""}
          {data.marriageDate && data.marriagePlace ? " · " : ""}
          {data.marriagePlace ?? ""}
        </div>
      ) : null}
    </div>
  );
}

const nodeTypes = { person: PersonCard, union: UnionNode };

export { buildLayout } from "./layout";

export function FamilyTreeGraph({
  graph,
  onSelect,
  selectedId,
}: {
  graph: TreeGraph;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
}) {
  // Drop sibling_of from the visual layer; the layout uses it during
  // generation assignment via inferSiblingParents but we never want to
  // render those edges (siblings are implied by shared parents).
  const filteredGraph = useMemo<TreeGraph>(
    () => ({
      persons: graph.persons,
      relationships: graph.relationships.filter((r) => r.type !== SIBLING_TYPE),
      couple_events: graph.couple_events ?? [],
    }),
    [graph],
  );
  const { nodes, edges } = useMemo(
    () =>
      buildLayout(
        {
          persons: filteredGraph.persons,
          relationships: graph.relationships,
          couple_events: graph.couple_events ?? [],
        },
        { onSelect, selectedId },
      ),
    [graph.relationships, graph.couple_events, filteredGraph.persons, onSelect, selectedId],
  );

  if (graph.persons.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-10 text-center text-sm text-muted-foreground">
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
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border)" />
        <Controls position="bottom-right" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
