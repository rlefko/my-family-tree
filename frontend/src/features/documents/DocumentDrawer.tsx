import { useQuery } from "@tanstack/react-query";
import { Download, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  documentDownloadUrl,
  documentRawUrl,
  useDeleteDocument,
  useDocument,
  useDocumentChunks,
  useDocumentText,
  useReprocessDocument,
  type DocumentDetail,
} from "@/api/endpoints/documents";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { StatusBadge } from "@/features/documents/StatusBadge";
import { formatBytes, kindLabel } from "@/features/documents/constants";

type Props = {
  documentId: string | null;
  initialPage?: number | null;
  onClose: () => void;
};

export function DocumentDrawer({ documentId, initialPage, onClose }: Props) {
  const open = Boolean(documentId);
  const detail = useDocument(documentId);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const reprocess = useReprocessDocument();
  const deleteDoc = useDeleteDocument();

  function onDelete() {
    if (!documentId) return;
    deleteDoc.mutate(documentId, {
      onSuccess: () => {
        setConfirmDelete(false);
        onClose();
      },
    });
  }

  return (
    <Drawer open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DrawerContent width="w-full sm:w-[720px]">
        {documentId && detail.data ? (
          <DrawerBody
            doc={detail.data}
            initialPage={initialPage ?? null}
            onReprocess={() => reprocess.mutate(documentId)}
            reprocessing={reprocess.isPending}
            onDelete={() => setConfirmDelete(true)}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">
            {detail.isLoading ? "Loading..." : "No document selected"}
          </div>
        )}
      </DrawerContent>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete document?"
        description="This permanently removes the file, its extracted text, and its chunks. Existing claims that cite this document remain but become orphaned."
        confirmLabel="Delete"
        busy={deleteDoc.isPending}
        onConfirm={onDelete}
      />
    </Drawer>
  );
}

function DrawerBody({
  doc,
  initialPage,
  onReprocess,
  reprocessing,
  onDelete,
}: {
  doc: DocumentDetail;
  initialPage: number | null;
  onReprocess: () => void;
  reprocessing: boolean;
  onDelete: () => void;
}) {
  const showReprocess =
    doc.status === "failed" ||
    (doc.status === "pending" &&
      Date.now() - new Date(doc.imported_at).getTime() > 60_000);

  return (
    <>
      <DrawerHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <DrawerTitle className="truncate">
              <span title={doc.original_filename}>{doc.original_filename}</span>
            </DrawerTitle>
            <DrawerDescription>
              {kindLabel(doc.kind)} · {formatBytes(doc.byte_size)}
              {doc.pages ? ` · ${doc.pages} page${doc.pages === 1 ? "" : "s"}` : ""}
            </DrawerDescription>
          </div>
          <StatusBadge status={doc.status} />
        </div>
      </DrawerHeader>
      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="preview" className="flex h-full flex-col">
          <TabsList className="mx-6 mt-3 grid w-fit grid-cols-4">
            <TabsTrigger value="preview">Preview</TabsTrigger>
            <TabsTrigger value="text">Text</TabsTrigger>
            <TabsTrigger value="chunks">Chunks</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
          </TabsList>
          <TabsContent value="preview" className="flex-1 overflow-hidden px-6 py-3">
            <PreviewPane doc={doc} initialPage={initialPage ?? undefined} />
          </TabsContent>
          <TabsContent value="text" className="flex-1 overflow-y-auto px-6 py-3">
            <TextPane doc={doc} initialPage={initialPage ?? undefined} />
          </TabsContent>
          <TabsContent value="chunks" className="flex-1 overflow-y-auto px-6 py-3">
            <ChunksPane doc={doc} initialPage={initialPage ?? undefined} />
          </TabsContent>
          <TabsContent value="metadata" className="flex-1 overflow-y-auto px-6 py-3">
            <MetadataPane doc={doc} />
          </TabsContent>
        </Tabs>
      </div>
      <footer className="flex items-center justify-between gap-2 border-t border-zinc-200 px-6 py-3">
        <a
          href={documentDownloadUrl(doc.id)}
          download={doc.original_filename}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
        <div className="flex items-center gap-2">
          {showReprocess ? (
            <button
              type="button"
              onClick={onReprocess}
              disabled={reprocessing}
              className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-60"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {reprocessing ? "Queueing..." : "Reprocess"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      </footer>
    </>
  );
}

function PreviewPane({ doc, initialPage }: { doc: DocumentDetail; initialPage?: number }) {
  const url = documentRawUrl(doc.id);
  if (doc.mime_type === "application/pdf" || doc.kind === "pdf_text" || doc.kind === "pdf_scan") {
    const src = initialPage ? `${url}#page=${initialPage}` : url;
    return (
      <iframe
        src={src}
        className="h-full w-full rounded border"
        title={doc.original_filename}
        sandbox="allow-same-origin allow-popups"
      />
    );
  }
  if (doc.mime_type.startsWith("image/") || doc.kind === "image") {
    return (
      <div className="flex h-full items-center justify-center">
        <img
          src={url}
          alt={doc.original_filename}
          className="max-h-full max-w-full object-contain"
        />
      </div>
    );
  }
  if (doc.mime_type.startsWith("text/") || doc.kind === "text" || doc.kind === "gedcom") {
    return <RawTextPreview docId={doc.id} />;
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-zinc-500">
      <p>Preview unavailable for this file type.</p>
    </div>
  );
}

function RawTextPreview({ docId }: { docId: string }) {
  const q = useQuery({
    queryKey: ["documents", docId, "raw-text"],
    queryFn: async () => {
      const res = await fetch(documentRawUrl(docId));
      if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
      return await res.text();
    },
  });
  if (q.isLoading) return <p className="text-sm text-zinc-500">Loading...</p>;
  if (q.error) return <p className="text-sm text-red-600">Failed to load preview</p>;
  return (
    <pre className="h-full overflow-auto whitespace-pre-wrap rounded border bg-zinc-50 p-3 font-mono text-xs">
      {q.data}
    </pre>
  );
}

function TextPane({ doc, initialPage }: { doc: DocumentDetail; initialPage?: number }) {
  const [page, setPage] = useState<number>(initialPage ?? 1);
  const text = useDocumentText(doc.id, { page, limit: 50 });
  if (!doc.text_count) {
    return (
      <p className="text-sm italic text-zinc-500">
        {doc.status === "ready" ? "No extracted text." : "Still processing..."}
      </p>
    );
  }
  const pages = doc.pages ?? 1;
  return (
    <div className="flex flex-col gap-3">
      {pages > 1 ? (
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded border border-zinc-300 px-2 py-0.5 disabled:opacity-50"
          >
            Prev
          </button>
          <span>
            Page {page} / {pages}
          </span>
          <button
            type="button"
            disabled={page >= pages}
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            className="rounded border border-zinc-300 px-2 py-0.5 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
      {text.isLoading ? <p className="text-xs text-zinc-500">Loading...</p> : null}
      {text.data?.items.map((row) => (
        <article key={row.id} className="rounded border border-zinc-200 bg-white p-3">
          <div className="mb-1 flex items-center gap-2">
            {row.page ? <Badge variant="secondary">p.{row.page}</Badge> : null}
            <Badge variant="outline" className="text-[10px]">
              {row.extraction_method}
            </Badge>
          </div>
          <pre className="whitespace-pre-wrap text-xs text-zinc-800">{row.content}</pre>
        </article>
      ))}
    </div>
  );
}

function ChunksPane({ doc, initialPage }: { doc: DocumentDetail; initialPage?: number }) {
  const chunks = useDocumentChunks(doc.id, {
    limit: 50,
    page: initialPage ?? undefined,
  });
  if (!doc.chunk_count) {
    return (
      <p className="text-sm italic text-zinc-500">
        {doc.status === "ready" ? "No chunks." : "Chunks generated after extraction completes."}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {chunks.data?.items.map((c) => (
        <div key={c.id} className="rounded border border-zinc-200 bg-white p-3">
          <div className="mb-1 flex items-center gap-2 text-[11px] text-zinc-500">
            <Badge variant="secondary">#{c.seq}</Badge>
            {c.page ? <Badge variant="outline">p.{c.page}</Badge> : null}
            <span>{c.tokens} tokens</span>
            <span>{c.kind}</span>
            {c.embedded ? (
              <span className="text-emerald-600">embedded</span>
            ) : (
              <span className="text-amber-600">awaiting embed</span>
            )}
          </div>
          <p className="text-xs text-zinc-800">
            {c.content.length > 600 ? `${c.content.slice(0, 600)}...` : c.content}
          </p>
        </div>
      ))}
    </div>
  );
}

function MetadataPane({ doc }: { doc: DocumentDetail }) {
  return (
    <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
      <Row label="Kind" value={kindLabel(doc.kind)} />
      <Row label="MIME" value={doc.mime_type} />
      <Row label="Size" value={formatBytes(doc.byte_size)} />
      <Row label="Pages" value={doc.pages ?? "-"} />
      <Row label="OCR" value={doc.ocr_engine ?? "-"} />
      <Row label="Lang" value={doc.language ?? "-"} />
      <Row
        label="SHA256"
        value={
          <Tooltip content={doc.sha256}>
            <code className="cursor-help">{doc.sha256.slice(0, 12)}...</code>
          </Tooltip>
        }
      />
      <Row label="Imported" value={new Date(doc.imported_at).toLocaleString()} />
      <Row
        label="Processed"
        value={doc.processed_at ? new Date(doc.processed_at).toLocaleString() : "-"}
      />
      {doc.error ? (
        <div className="col-span-3 rounded border border-red-200 bg-red-50 p-2 text-red-700">
          <strong className="font-semibold">Error:</strong> {doc.error}
        </div>
      ) : null}
      {doc.vision_calls.length > 0 ? (
        <div className="col-span-3">
          <div className="mb-1 font-semibold text-zinc-700">Vision calls</div>
          <ul className="ml-4 list-disc space-y-0.5">
            {doc.vision_calls.map((v) => (
              <li key={`${v.page}-${v.model}-${v.cost_usd}`}>
                p.{v.page} · ${v.cost_usd.toFixed(4)} · {v.model}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </dl>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <dt className="font-medium text-zinc-500">{label}</dt>
      <dd className="col-span-2 break-words text-zinc-800">{value}</dd>
    </>
  );
}
