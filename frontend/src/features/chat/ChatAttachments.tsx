import { Loader2, Paperclip, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { DocumentKind } from "@/features/documents/constants";
import { cn } from "@/lib/utils";

export type ChatAttachment = {
  tempId: string;
  filename: string;
  status: "uploading" | "ready" | "failed";
  progress: number;
  documentId?: string;
  mimeType?: string;
  kind?: DocumentKind;
  error?: string;
};

export function ChatAttachments({
  items,
  onRemove,
}: {
  items: ChatAttachment[];
  onRemove: (tempId: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-1.5">
      {items.map((it) => (
        <Tooltip
          key={it.tempId}
          content={
            it.status === "failed"
              ? (it.error ?? "Upload failed")
              : it.status === "uploading"
                ? `Uploading ${Math.round(it.progress * 100)}%`
                : it.documentId
                  ? `Ready · ${it.documentId.slice(0, 8)}`
                  : "Ready"
          }
        >
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
              it.status === "uploading"
                ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                : it.status === "ready"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-red-200 bg-red-50 text-red-700",
            )}
          >
            {it.status === "uploading" ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Paperclip className="h-3 w-3" />
            )}
            <span className="max-w-[180px] truncate">{it.filename}</span>
            {it.status === "uploading" ? (
              <Badge variant="secondary" className="text-[10px]">
                {Math.round(it.progress * 100)}%
              </Badge>
            ) : null}
            <button
              type="button"
              aria-label="Remove attachment"
              onClick={() => onRemove(it.tempId)}
              className="ml-0.5 text-current opacity-60 hover:opacity-100"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </Tooltip>
      ))}
    </div>
  );
}
