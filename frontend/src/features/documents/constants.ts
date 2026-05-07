// Mirrors backend `MAX_UPLOAD_BYTES`. Keep in sync; client-side check is a UX
// short-circuit, the server is authoritative.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function kindLabel(kind: string): string {
  return (
    {
      pdf_text: "PDF",
      pdf_scan: "Scanned PDF",
      image: "Image",
      text: "Text",
      gedcom: "GEDCOM",
      note: "Note",
      web: "Web",
    }[kind] ?? kind
  );
}
