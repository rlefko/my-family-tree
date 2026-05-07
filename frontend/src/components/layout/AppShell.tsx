import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  FileText,
  Home,
  ListChecks,
  MessageCircle,
  Network,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { useHealth } from "@/api/endpoints/health";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

const NAV: {
  to: "/" | "/people" | "/tree" | "/documents" | "/conflicts" | "/proposals" | "/chat";
  label: string;
  icon: LucideIcon;
}[] = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/tree", label: "Tree", icon: Network },
  { to: "/people", label: "People", icon: Users },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/conflicts", label: "Conflicts", icon: AlertTriangle },
  { to: "/proposals", label: "Proposals", icon: ListChecks },
  { to: "/chat", label: "Chat", icon: MessageCircle },
];

export function AppShell({ children }: { children: ReactNode }) {
  const health = useHealth();
  return (
    <div className="flex h-full">
      <aside className="flex w-56 flex-col border-r border-zinc-200 bg-white">
        <div className="px-4 py-4 text-lg font-semibold">{env.VITE_APP_NAME}</div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-2 rounded px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-100",
                )}
                activeProps={{ className: "bg-zinc-100 font-medium text-zinc-900" }}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
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
