import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type ApiError } from "@/api/client";
import {
  isTerminalStatus,
  type DocumentKind,
  type DocumentStatus,
} from "@/features/documents/constants";
import { env } from "@/lib/env";

export type DocumentRow = {
  id: string;
  kind: DocumentKind;
  original_filename: string;
  status: DocumentStatus;
  pages?: number | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  created_at?: string | null;
  processed_at?: string | null;
  error?: string | null;
};

export type DocumentList = { items: DocumentRow[]; total: number };

export type DocumentCreated = {
  document_id: string;
  sha256: string;
  kind: DocumentKind;
  status: DocumentStatus;
  mime_type: string;
  original_filename: string;
};

export type DocumentDetail = {
  id: string;
  kind: DocumentKind;
  mime_type: string;
  byte_size: number;
  sha256: string;
  original_filename: string;
  status: DocumentStatus;
  pages?: number | null;
  language?: string | null;
  ocr_engine?: string | null;
  error?: string | null;
  attempts: number;
  imported_at: string;
  processed_at?: string | null;
  text_count: number;
  chunk_count: number;
  vision_calls: { page: number; cost_usd: number; model: string }[];
};

export type DocumentTextRow = {
  id: string;
  page: number | null;
  extraction_method: string;
  content: string;
  created_at: string;
};

export type DocumentTextList = { items: DocumentTextRow[]; total: number };

export type ChunkRow = {
  id: string;
  seq: number;
  page: number | null;
  kind: string;
  tokens: number;
  content: string;
  embedded: boolean;
};

export type ChunkList = { items: ChunkRow[]; total: number };

export type DocumentListFilters = {
  kind?: string;
  status?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export type DocumentDeleted = { id: string; deleted: boolean; orphaned_sources_count: number };

export type DocumentReprocessed = { id: string; status: string; job_id: string | null };

function buildListQuery(filters?: DocumentListFilters): string {
  const params = new URLSearchParams();
  if (filters?.kind) params.set("kind", filters.kind);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.q) params.set("q", filters.q);
  if (filters?.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters?.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useDocuments(filters?: DocumentListFilters) {
  return useQuery({
    queryKey: ["documents", filters ?? {}],
    queryFn: () => apiFetch<DocumentList>(`/api/v1/documents${buildListQuery(filters)}`),
  });
}

export function useDocument(id: string | null | undefined) {
  return useQuery({
    queryKey: ["documents", id, "detail"],
    queryFn: () => apiFetch<DocumentDetail>(`/api/v1/documents/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isTerminalStatus(status)) return false;
      return 3_000;
    },
  });
}

export function useDocumentText(
  id: string | null | undefined,
  paging: { page?: number; limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams();
  if (paging.page !== undefined) params.set("page", String(paging.page));
  if (paging.limit !== undefined) params.set("limit", String(paging.limit));
  if (paging.offset !== undefined) params.set("offset", String(paging.offset));
  const qs = params.toString();
  return useQuery({
    queryKey: ["documents", id, "text", paging],
    queryFn: () => apiFetch<DocumentTextList>(`/api/v1/documents/${id}/text${qs ? `?${qs}` : ""}`),
    enabled: Boolean(id),
  });
}

export function useDocumentChunks(
  id: string | null | undefined,
  paging: { page?: number; limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams();
  if (paging.page !== undefined) params.set("page", String(paging.page));
  if (paging.limit !== undefined) params.set("limit", String(paging.limit));
  if (paging.offset !== undefined) params.set("offset", String(paging.offset));
  const qs = params.toString();
  return useQuery({
    queryKey: ["documents", id, "chunks", paging],
    queryFn: () => apiFetch<ChunkList>(`/api/v1/documents/${id}/chunks${qs ? `?${qs}` : ""}`),
    enabled: Boolean(id),
  });
}

export type UploadDocumentInput = {
  file: File;
  treeId: string;
  kind?: string;
  onProgress?: (loaded: number, total: number) => void;
  signal?: AbortSignal;
};

export function buildUploadFormData({
  file,
  treeId,
  kind,
}: {
  file: File;
  treeId: string;
  kind?: string;
}): FormData {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("tree_id", treeId);
  if (kind) fd.append("kind", kind);
  return fd;
}

export function uploadDocumentRequest(input: UploadDocumentInput): Promise<DocumentCreated> {
  const fd = buildUploadFormData(input);
  return new Promise<DocumentCreated>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${env.VITE_API_BASE_URL}/api/v1/documents`);
    xhr.setRequestHeader("X-Request-ID", crypto.randomUUID());
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && input.onProgress) input.onProgress(e.loaded, e.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as DocumentCreated);
        } catch (e) {
          reject({
            status: xhr.status,
            code: "parse_error",
            message: (e as Error).message,
          } as ApiError);
        }
      } else {
        let code = "unknown";
        let message = xhr.statusText || `HTTP ${xhr.status}`;
        try {
          const body = JSON.parse(xhr.responseText) as {
            error?: { code?: string; message?: string };
          };
          code = body.error?.code ?? code;
          message = body.error?.message ?? message;
        } catch {
          // body wasn't JSON
        }
        reject({ status: xhr.status, code, message } as ApiError);
      }
    });
    xhr.addEventListener("error", () =>
      reject({ status: 0, code: "network_error", message: "upload failed" } as ApiError),
    );
    xhr.addEventListener("abort", () =>
      reject({ status: 0, code: "aborted", message: "upload aborted" } as ApiError),
    );
    if (input.signal) {
      input.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(fd);
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UploadDocumentInput) => uploadDocumentRequest(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<DocumentDeleted>(`/api/v1/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useReprocessDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<DocumentReprocessed>(`/api/v1/documents/${id}/reprocess`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["documents", id, "detail"] });
    },
  });
}

export function documentRawUrl(id: string): string {
  return `${env.VITE_API_BASE_URL}/api/v1/documents/${id}/raw`;
}

export function documentDownloadUrl(id: string): string {
  return `${env.VITE_API_BASE_URL}/api/v1/documents/${id}/download`;
}
