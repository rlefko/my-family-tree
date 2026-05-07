import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ACTIVE = new Set(["pending", "extracting", "embedding", "extracting_claims"]);

const LABELS: Record<string, string> = {
  pending: "Pending",
  extracting: "Extracting",
  embedding: "Embedding",
  extracting_claims: "Linking",
  ready: "Ready",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: string }) {
  const label = LABELS[status] ?? status;
  const tone =
    status === "ready"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : status === "failed"
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  return (
    <Badge
      variant="outline"
      className={cn(tone, ACTIVE.has(status) ? "animate-pulse" : "", "font-medium")}
    >
      {label}
    </Badge>
  );
}
