import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export type ChunkSearchInput = {
  tree_id: string;
  query: string;
  k?: number;
  document_id?: string;
};

export type ChunkSearchHit = {
  chunk_id: string;
  document_id: string;
  document_filename: string | null;
  document_kind: string | null;
  page: number | null;
  content: string;
  score: number;
};

export type ChunkSearchResponse = { items: ChunkSearchHit[] };

export function useChunkSearch() {
  return useMutation({
    mutationFn: (input: ChunkSearchInput) =>
      apiFetch<ChunkSearchResponse>("/api/v1/search/chunks", {
        method: "POST",
        body: JSON.stringify(input),
      }),
  });
}
