import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  FileText,
  Image as ImageIcon,
  Loader2,
  MoreVertical,
  Search as SearchIcon,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  documentDownloadUrl,
  useDeleteDocument,
  useDocuments,
  useReprocessDocument,
  type DocumentRow,
} from "@/api/endpoints/documents";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { DocumentDrawer } from "@/features/documents/DocumentDrawer";
import { DocumentSearch } from "@/features/documents/DocumentSearch";
import { UploadDropzone, type UploadDropzoneHandle } from "@/features/documents/UploadDropzone";
import { StatusBadge } from "@/features/documents/StatusBadge";
import {
  DOCUMENT_KINDS,
  DOCUMENT_STATUSES,
  formatBytes,
  isActiveStatus,
  kindLabel,
} from "@/features/documents/constants";
import { DEFAULT_TREE_ID } from "@/lib/tree";
import { cn } from "@/lib/utils";

type DocumentsSearch = {
  id?: string;
  page?: number;
  q?: string;
  kind?: string;
  status?: string;
};

export const Route = createFileRoute("/documents")({
  component: DocumentsPage,
  validateSearch: (search: Record<string, unknown>): DocumentsSearch => {
    const pageRaw = search.page;
    const page =
      typeof pageRaw === "number"
        ? pageRaw
        : typeof pageRaw === "string" && /^\d+$/.test(pageRaw)
          ? Number(pageRaw)
          : undefined;
    return {
      id: typeof search.id === "string" ? search.id : undefined,
      page,
      q: typeof search.q === "string" ? search.q : undefined,
      kind: typeof search.kind === "string" ? search.kind : undefined,
      status: typeof search.status === "string" ? search.status : undefined,
    };
  },
});

function DocumentsPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/documents" });
  const dropzone = useRef<UploadDropzoneHandle | null>(null);
  const [qDraft, setQDraft] = useState(search.q ?? "");

  // Debounce search input writes to URL.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      if ((qDraft || undefined) === search.q) return;
      void navigate({
        search: (prev) => ({ ...prev, q: qDraft || undefined }),
      });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [qDraft, navigate, search.q]);

  const filters = useMemo(
    () => ({ kind: search.kind, status: search.status, q: search.q, limit: 100 }),
    [search.kind, search.status, search.q],
  );
  const docs = useDocuments(filters);
  const items = docs.data?.items ?? [];

  function setFilter(patch: Partial<DocumentsSearch>) {
    void navigate({
      search: (prev) => ({ ...prev, ...patch }),
    });
  }

  function openDoc(id: string, page: number | null) {
    void navigate({
      search: (prev) => ({ ...prev, id, page: page ?? undefined }),
    });
  }

  function closeDoc() {
    void navigate({
      search: (prev) => ({ ...prev, id: undefined, page: undefined }),
    });
  }

  return (
    <section className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border bg-card px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Documents</h1>
          <p className="text-xs text-muted-foreground">
            Upload PDFs, scans, photos, GEDCOM, and text. They are extracted, embedded, and
            searchable inside chat as soon as they are ready.
          </p>
        </div>
        <button
          type="button"
          onClick={() => dropzone.current?.pickFiles()}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90"
        >
          <Upload className="h-3.5 w-3.5" />
          Upload
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mb-4 flex items-center gap-2">
          <div className="relative flex-1">
            <SearchIcon className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={qDraft}
              onChange={(e) => setQDraft(e.target.value)}
              placeholder="Filter by filename or MIME type"
              className="pl-7"
            />
          </div>
          <select
            value={search.kind ?? ""}
            onChange={(e) => setFilter({ kind: e.target.value || undefined })}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
          >
            <option value="">All kinds</option>
            {DOCUMENT_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </select>
          <select
            value={search.status ?? ""}
            onChange={(e) => setFilter({ status: e.target.value || undefined })}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
          >
            <option value="">All statuses</option>
            {DOCUMENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-4">
          <DocumentSearch onPickResult={openDoc} />
        </div>

        {docs.isLoading ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState onUpload={() => dropzone.current?.pickFiles()} />
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {items.map((doc) => (
              <li key={doc.id}>
                <DocumentCard
                  doc={doc}
                  onOpen={() => openDoc(doc.id, null)}
                  highlighted={doc.id === search.id}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      <UploadDropzone ref={dropzone} treeId={DEFAULT_TREE_ID} />
      <DocumentDrawer
        documentId={search.id ?? null}
        initialPage={search.page ?? null}
        onClose={closeDoc}
      />
    </section>
  );
}

function DocumentCard({
  doc,
  onOpen,
  highlighted,
}: {
  doc: DocumentRow;
  onOpen: () => void;
  highlighted: boolean;
}) {
  const reprocess = useReprocessDocument();
  const deleteDoc = useDeleteDocument();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const Icon = doc.kind === "image" ? ImageIcon : FileText;
  const showReprocess = doc.status === "failed";
  const isActive = isActiveStatus(doc.status);

  return (
    <Card
      className={cn(
        "cursor-pointer overflow-hidden transition hover:border-primary/40",
        highlighted ? "border-primary/60 ring-1 ring-primary/30" : "",
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1" role="button" tabIndex={0} onClick={onOpen}>
            <p
              className="truncate text-sm font-medium text-foreground"
              title={doc.original_filename}
            >
              {doc.original_filename}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className="text-[10px]">
                {kindLabel(doc.kind)}
              </Badge>
              <StatusBadge status={doc.status} />
              {isActive ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary" aria-hidden />
              ) : null}
            </div>
            <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
              <span>{doc.size_bytes ? formatBytes(doc.size_bytes) : ""}</span>
              {doc.pages ? (
                <span>
                  {doc.pages} page{doc.pages === 1 ? "" : "s"}
                </span>
              ) : null}
              {doc.created_at ? <span>{new Date(doc.created_at).toLocaleDateString()}</span> : null}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="Document actions"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <MoreVertical className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <a href={documentDownloadUrl(doc.id)} download={doc.original_filename}>
                  Download
                </a>
              </DropdownMenuItem>
              {showReprocess ? (
                <DropdownMenuItem
                  onSelect={() => {
                    reprocess.mutate(doc.id);
                  }}
                >
                  Reprocess
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem
                onSelect={(e) => {
                  e.preventDefault();
                  setConfirmDelete(true);
                }}
                className="text-destructive focus:text-destructive"
              >
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardContent>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete document?"
        description={`Permanently remove "${doc.original_filename}" and its extracted text and chunks.`}
        confirmLabel="Delete"
        busy={deleteDoc.isPending}
        onConfirm={() => {
          deleteDoc.mutate(doc.id, { onSuccess: () => setConfirmDelete(false) });
        }}
      />
    </Card>
  );
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="mx-auto mt-12 flex max-w-md flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border bg-card px-6 py-10 text-center">
      <div className="rounded-full bg-primary/10 p-3 text-primary">
        <Upload className="h-6 w-6" />
      </div>
      <h2 className="text-base font-semibold text-foreground">No documents yet</h2>
      <p className="text-sm text-muted-foreground">
        Drop files here or click Upload to get started. PDFs, photos, scans, GEDCOM, and plain text
        are all supported.
      </p>
      <button
        type="button"
        onClick={onUpload}
        className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90"
      >
        <Upload className="h-3.5 w-3.5" />
        Upload your first document
      </button>
    </div>
  );
}
