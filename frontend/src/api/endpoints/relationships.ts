import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type PersonNode = {
  id: string;
  display_name: string;
  surname: string | null;
  sex: "male" | "female" | "unknown";
  birth_text: string | null;
  death_text: string | null;
  is_living: boolean;
};

export type RelationshipRow = {
  id: string;
  subject_id: string;
  object_id: string;
  type:
    | "parent_of"
    | "spouse_of"
    | "sibling_of"
    | "adoptive_parent_of"
    | "step_parent_of"
    | "guardian_of"
    | "partner_of";
  confidence: number;
};

export type TreeGraph = {
  persons: PersonNode[];
  relationships: RelationshipRow[];
};

export function useTreeGraph() {
  return useQuery({
    queryKey: ["tree-graph"],
    queryFn: () => apiFetch<TreeGraph>("/api/v1/relationships"),
    refetchInterval: 10_000,
  });
}
