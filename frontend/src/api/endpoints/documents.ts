import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type DocumentRow = {
  id: string;
  kind: string;
  original_filename: string;
  status: string;
  pages?: number | null;
};

export type DocumentList = { items: DocumentRow[] };

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => apiFetch<DocumentList>("/api/v1/documents"),
  });
}
