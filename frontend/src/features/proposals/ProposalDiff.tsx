import type { ProposalRow } from "@/api/endpoints/proposals";

export function ProposalDiff({ proposal }: { proposal: ProposalRow }) {
  const payload = proposal.payload ?? {};
  const entries = Object.entries(payload);
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">Proposed payload</div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">(empty payload)</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key} className="border-b border-border last:border-0">
                <td className="w-48 py-1 pr-4 align-top font-mono text-xs text-muted-foreground">
                  {key}
                </td>
                <td className="py-1 align-top text-foreground">
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs">
                    {format(value)}
                  </pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {proposal.rationale ? (
        <div className="mt-3 rounded border border-border bg-muted p-2 text-xs italic text-foreground">
          <span className="font-semibold not-italic">Rationale: </span>
          {proposal.rationale}
        </div>
      ) : null}
    </div>
  );
}

function format(value: unknown): string {
  if (value === null) return "(null)";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
