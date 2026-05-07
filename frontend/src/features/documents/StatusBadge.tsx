import { Badge } from "@/components/ui/badge";
import {
  isActiveStatus,
  statusLabel,
  type DocumentStatus,
} from "@/features/documents/constants";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const tone =
    status === "ready"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : status === "failed"
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  return (
    <Badge
      variant="outline"
      className={cn(tone, isActiveStatus(status) ? "animate-pulse" : "", "font-medium")}
    >
      {statusLabel(status)}
    </Badge>
  );
}
