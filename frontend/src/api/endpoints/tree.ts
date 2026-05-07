import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type TreeStats = {
  persons: number;
  events: number;
  relationships: number;
  documents: number;
  conflicts_open: number;
  proposals_pending: number;
};

export function useTreeStats() {
  return useQuery({
    queryKey: ["tree", "stats"],
    queryFn: () => apiFetch<TreeStats>("/api/v1/tree/stats"),
  });
}
