import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type ConflictRow = {
  id: string;
  kind: string;
  status: string;
  severity: number;
  summary: string;
  subject_id: string;
  subject_type: string;
};

export type ConflictList = { items: ConflictRow[] };

export function useConflicts() {
  return useQuery({
    queryKey: ["conflicts"],
    queryFn: () => apiFetch<ConflictList>("/api/v1/conflicts"),
  });
}
