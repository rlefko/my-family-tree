import { cn } from "@/lib/utils";

import type { ToolCall } from "./useChatStream";

const STATUS_LABEL: Record<ToolCall["status"], string> = {
  running: "running",
  ok: "ok",
  error: "error",
};

const STATUS_CLASS: Record<ToolCall["status"], string> = {
  running: "bg-amber-100 text-amber-800",
  ok: "bg-emerald-100 text-emerald-800",
  error: "bg-red-100 text-red-800",
};

export function ToolCallCard({ call }: { call: ToolCall }) {
  return (
    <details className="group rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs">
      <summary className="flex cursor-pointer items-center gap-2 text-zinc-700 marker:hidden">
        <span className="font-mono">{call.name}</span>
        <span className={cn("rounded-full px-2 py-0.5 text-[10px]", STATUS_CLASS[call.status])}>
          {STATUS_LABEL[call.status]}
        </span>
        <span className="ml-auto text-zinc-400 group-open:rotate-180 transition-transform">▾</span>
      </summary>
      {call.input !== undefined ? <Section label="Input" value={call.input} /> : null}
      {call.output !== undefined ? <Section label="Output" value={call.output} /> : null}
    </details>
  );
}

function Section({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <pre className="overflow-x-auto rounded bg-white p-2 text-[11px] leading-snug text-zinc-800">
        {format(value)}
      </pre>
    </div>
  );
}

function format(v: unknown): string {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
