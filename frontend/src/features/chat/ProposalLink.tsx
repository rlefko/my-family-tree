import { Link } from "@tanstack/react-router";

export function ProposalLink({ ids }: { ids: string[] }) {
  if (ids.length === 0) return null;
  const search = ids.join(",");
  return (
    <Link
      to="/proposals"
      search={{ ids: search }}
      className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
    >
      <span>📋</span>
      <span>
        Queued {ids.length} proposal{ids.length === 1 ? "" : "s"} - review
      </span>
    </Link>
  );
}
