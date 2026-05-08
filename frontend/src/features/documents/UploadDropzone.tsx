import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload, X } from "lucide-react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import {
  uploadDocumentRequest,
  useDocument,
  type DocumentCreated,
} from "@/api/endpoints/documents";
import { Progress } from "@/components/ui/progress";
import type { ApiError } from "@/api/client";
import { MAX_UPLOAD_BYTES, formatBytes } from "@/features/documents/constants";
import { cn } from "@/lib/utils";

type ItemStatus = "uploading" | "processing" | "ready" | "failed";

type UploadingItem = {
  id: string;
  file: File;
  status: ItemStatus;
  progress: number;
  documentId?: string;
  error?: string;
  abort?: AbortController;
};

export type UploadDropzoneHandle = {
  pickFiles: () => void;
  enqueue: (files: File[]) => void;
};

type Props = {
  treeId: string;
  // When true, the full-page drag overlay is shown while files are dragged.
  // Set to false when embedded in a context (like the chat input) where the
  // host already has its own drag UI.
  showOverlay?: boolean;
};

export const UploadDropzone = forwardRef<UploadDropzoneHandle, Props>(function UploadDropzone(
  { treeId, showOverlay = true },
  ref,
) {
  const qc = useQueryClient();
  const [items, setItems] = useState<UploadingItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const enqueue = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const id = crypto.randomUUID();
        if (file.size > MAX_UPLOAD_BYTES) {
          setItems((prev) => [
            ...prev,
            {
              id,
              file,
              status: "failed",
              progress: 0,
              error: `File too large (max ${formatBytes(MAX_UPLOAD_BYTES)})`,
            },
          ]);
          continue;
        }
        const abort = new AbortController();
        setItems((prev) => [...prev, { id, file, status: "uploading", progress: 0, abort }]);
        uploadDocumentRequest({
          file,
          treeId,
          signal: abort.signal,
          onProgress: (loaded, total) => {
            setItems((prev) =>
              prev.map((it) =>
                it.id === id ? { ...it, progress: total > 0 ? loaded / total : 0 } : it,
              ),
            );
          },
        })
          .then((doc: DocumentCreated) => {
            setItems((prev) =>
              prev.map((it) =>
                it.id === id
                  ? { ...it, status: "processing", progress: 1, documentId: doc.document_id }
                  : it,
              ),
            );
            qc.invalidateQueries({ queryKey: ["documents"] });
          })
          .catch((err: ApiError) => {
            setItems((prev) =>
              prev.map((it) =>
                it.id === id ? { ...it, status: "failed", error: err.message } : it,
              ),
            );
          });
      }
    },
    [qc, treeId],
  );

  const pickFiles = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  useImperativeHandle(ref, () => ({ pickFiles, enqueue }), [pickFiles, enqueue]);

  // Window-level drag overlay tracking. Counter pattern so child elements do
  // not flicker the overlay on drag enter/leave.
  useEffect(() => {
    if (!showOverlay) return;
    function onDragEnter(e: DragEvent) {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      dragDepth.current += 1;
      setDragging(true);
    }
    function onDragLeave() {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    }
    function onDragOver(e: DragEvent) {
      if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
    }
    function onDrop(e: DragEvent) {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const files = Array.from(e.dataTransfer.files ?? []);
      if (files.length > 0) enqueue(files);
    }
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [enqueue, showOverlay]);

  function dismiss(id: string) {
    setItems((prev) => {
      const target = prev.find((it) => it.id === id);
      target?.abort?.abort();
      return prev.filter((it) => it.id !== id);
    });
  }

  function onTerminal(id: string, status: ItemStatus, error?: string) {
    setItems((prev) =>
      prev.map((it) =>
        it.id === id
          ? {
              ...it,
              status,
              error: error ?? it.error,
              progress: status === "ready" ? 1 : it.progress,
            }
          : it,
      ),
    );
    qc.invalidateQueries({ queryKey: ["documents"] });
    if (status === "ready") {
      window.setTimeout(() => dismiss(id), 5_000);
    }
  }

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) enqueue(files);
          e.currentTarget.value = "";
        }}
      />
      {showOverlay && dragging ? (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-indigo-600/10 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-indigo-500 bg-white px-8 py-6 text-indigo-700 shadow-xl">
            <Upload className="h-8 w-8" />
            <p className="text-sm font-medium">Drop files to upload</p>
          </div>
        </div>
      ) : null}
      {items.length > 0 ? (
        <aside className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
          {items.map((it) => (
            <div
              key={it.id}
              className={cn(
                "rounded-md border bg-white px-3 py-2 shadow",
                it.status === "failed" ? "border-red-200" : "border-zinc-200",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium" title={it.file.name}>
                  {it.file.name}
                </span>
                <button
                  type="button"
                  onClick={() => dismiss(it.id)}
                  aria-label="Dismiss"
                  className="text-zinc-400 hover:text-zinc-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <UploadStatusLine item={it} />
              {it.status === "uploading" || it.status === "processing" ? (
                <Progress value={Math.round(it.progress * 100)} className="mt-2 h-1" />
              ) : null}
              {it.status === "processing" && it.documentId ? (
                <DocumentStatusWatcher
                  id={it.documentId}
                  onTerminal={(status, error) => onTerminal(it.id, status, error)}
                />
              ) : null}
            </div>
          ))}
        </aside>
      ) : null}
    </>
  );
});

function UploadStatusLine({ item }: { item: UploadingItem }) {
  if (item.status === "uploading") {
    return (
      <p className="mt-1 text-xs text-zinc-500">Uploading {Math.round(item.progress * 100)}%</p>
    );
  }
  if (item.status === "processing") {
    return (
      <p className="mt-1 inline-flex items-center gap-1 text-xs text-indigo-600">
        <Loader2 className="h-3 w-3 animate-spin" />
        Processing...
      </p>
    );
  }
  if (item.status === "ready") {
    return <p className="mt-1 text-xs text-emerald-600">Ready</p>;
  }
  return (
    <p className="mt-1 text-xs text-red-600" title={item.error ?? ""}>
      {item.error ?? "Failed"}
    </p>
  );
}

function DocumentStatusWatcher({
  id,
  onTerminal,
}: {
  id: string;
  onTerminal: (status: ItemStatus, error?: string) => void;
}) {
  const detail = useDocument(id);
  useEffect(() => {
    const status = detail.data?.status;
    if (status === "ready") onTerminal("ready");
    else if (status === "failed") onTerminal("failed", detail.data?.error ?? "ingest failed");
  }, [detail.data?.status, detail.data?.error, onTerminal]);
  return null;
}
