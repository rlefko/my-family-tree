import { Search } from "lucide-react";
import { useState } from "react";

import { useChunkSearch, type ChunkSearchHit } from "@/api/endpoints/search";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { kindLabel } from "@/features/documents/constants";
import { DEFAULT_TREE_ID } from "@/lib/tree";

type Props = {
  documentId?: string;
  onPickResult: (documentId: string, page: number | null) => void;
};

export function DocumentSearch({ documentId, onPickResult }: Props) {
  const [query, setQuery] = useState("");
  const search = useChunkSearch();

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    search.mutate({ tree_id: DEFAULT_TREE_ID, query: trimmed, k: 10, document_id: documentId });
  }

  const tokens = query
    .trim()
    .split(/\s+/)
    .filter((t) => t.length > 1);

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3">
      <form onSubmit={onSubmit} className="flex items-center gap-2">
        <Search className="h-4 w-4 text-zinc-400" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search inside documents (text + visual descriptions)"
          className="flex-1"
        />
        <button
          type="submit"
          disabled={search.isPending || query.trim().length === 0}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {search.isPending ? "Searching..." : "Search"}
        </button>
      </form>
      {search.isPending ? (
        <ul className="mt-3 space-y-2">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-14 animate-pulse rounded border border-zinc-100 bg-zinc-50" />
          ))}
        </ul>
      ) : null}
      {search.error ? (
        <p className="mt-3 rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
          Search failed: {(search.error as { message?: string }).message ?? String(search.error)}
        </p>
      ) : null}
      {search.data && search.data.items.length === 0 ? (
        <p className="mt-3 text-xs italic text-zinc-500">No matches.</p>
      ) : null}
      {search.data && search.data.items.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {search.data.items.map((hit) => (
            <li key={hit.chunk_id}>
              <ResultCard hit={hit} tokens={tokens} onPick={onPickResult} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ResultCard({
  hit,
  tokens,
  onPick,
}: {
  hit: ChunkSearchHit;
  tokens: string[];
  onPick: (documentId: string, page: number | null) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(hit.document_id, hit.page)}
      className="flex w-full flex-col items-start gap-1 rounded border border-zinc-200 bg-white px-3 py-2 text-left hover:border-indigo-200 hover:bg-indigo-50/30"
    >
      <div className="flex w-full items-center gap-2 text-xs">
        <span className="truncate font-medium text-zinc-900">
          {hit.document_filename ?? hit.document_id}
        </span>
        {hit.document_kind ? (
          <Badge variant="outline" className="text-[10px]">
            {kindLabel(hit.document_kind)}
          </Badge>
        ) : null}
        {hit.page ? <Badge variant="secondary">p.{hit.page}</Badge> : null}
        <span className="ml-auto text-[10px] text-zinc-400">{(hit.score * 100).toFixed(0)}%</span>
      </div>
      <p className="line-clamp-3 text-xs text-zinc-700">
        <HighlightedSnippet text={hit.content} tokens={tokens} />
      </p>
    </button>
  );
}

function HighlightedSnippet({ text, tokens }: { text: string; tokens: string[] }) {
  if (tokens.length === 0) return <>{text}</>;
  const escaped = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(re);
  // Index-based keys are appropriate here: split() can produce duplicate
  // tokens, and the array is a static result of one regex split per render.
  return (
    <>
      {parts.map((part, i) => {
        const key = `${i}:${part.length}`;
        return re.test(part) ? (
          <mark key={key} className="rounded bg-amber-100 px-0.5">
            {part}
          </mark>
        ) : (
          <span key={key}>{part}</span>
        );
      })}
    </>
  );
}
