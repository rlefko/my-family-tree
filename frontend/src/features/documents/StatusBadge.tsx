import { Badge } from "@/components/ui/badge";
import { isActiveStatus, statusLabel, type DocumentStatus } from "@/features/documents/constants";
import { STATUS_BADGE_OUTLINE } from "@/lib/status-styles";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const tone = STATUS_BADGE_OUTLINE[status] ?? STATUS_BADGE_OUTLINE.pending;
  return (
    <Badge
      variant="outline"
      className={cn(tone, isActiveStatus(status) ? "animate-pulse" : "", "font-medium")}
    >
      {statusLabel(status)}
    </Badge>
  );
}
