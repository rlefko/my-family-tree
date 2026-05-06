import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useHealth } from "@/api/endpoints/health";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

const NAV: { to: "/" | "/people" | "/tree" | "/documents" | "/conflicts" | "/chat"; label: string }[] = [
  { to: "/", label: "Dashboard" },
  { to: "/tree", label: "Tree" },
  { to: "/people", label: "People" },
  { to: "/documents", label: "Documents" },
  { to: "/conflicts", label: "Conflicts" },
  { to: "/chat", label: "Chat" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const health = useHealth();
  return (
    <div className="flex h-full">
      <aside className="flex w-56 flex-col border-r border-zinc-200 bg-white">
        <div className="px-4 py-4 text-lg font-semibold">{env.VITE_APP_NAME}</div>
        <nav className="flex-1 space-y-1 px-2">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "block rounded px-3 py-2 text-sm hover:bg-zinc-100",
              )}
              activeProps={{ className: "bg-zinc-100 font-medium" }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500">
          {health.data ? (
            <>
              <div>db: {health.data.db}</div>
              <div>s3: {health.data.s3}</div>
              <div>
                llm: openai={health.data.llm.openai}, anthropic={health.data.llm.anthropic}
              </div>
            </>
          ) : (
            <div>Checking health...</div>
          )}
        </div>
      </aside>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
