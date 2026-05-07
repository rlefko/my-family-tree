// Mirrors backend `MAX_UPLOAD_BYTES`. Keep in sync; client-side check is a UX
// short-circuit, the server is authoritative.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

// Mirrors `ProcessingStatus` (backend enums). The arrays double as ordered
// option lists for filter selects.
export const DOCUMENT_STATUSES = [
  "pending",
  "extracting",
  "embedding",
  "extracting_claims",
  "ready",
  "failed",
] as const;
export type DocumentStatus = (typeof DOCUMENT_STATUSES)[number];

const ACTIVE_STATUSES = new Set<DocumentStatus>([
  "pending",
  "extracting",
  "embedding",
  "extracting_claims",
]);

export function isActiveStatus(status: DocumentStatus): boolean {
  return ACTIVE_STATUSES.has(status);
}

export function isTerminalStatus(status: DocumentStatus): boolean {
  return status === "ready" || status === "failed";
}

// Mirrors `DocumentKind`. Order matches the kinds users see most often first.
export const DOCUMENT_KINDS = [
  "pdf_text",
  "pdf_scan",
  "image",
  "text",
  "gedcom",
  "note",
  "web",
] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

const KIND_LABELS: Record<DocumentKind, string> = {
  pdf_text: "PDF",
  pdf_scan: "Scanned PDF",
  image: "Image",
  text: "Text",
  gedcom: "GEDCOM",
  note: "Note",
  web: "Web",
};

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: "Pending",
  extracting: "Extracting",
  embedding: "Embedding",
  extracting_claims: "Linking",
  ready: "Ready",
  failed: "Failed",
};

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind as DocumentKind] ?? kind;
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as DocumentStatus] ?? status;
}
