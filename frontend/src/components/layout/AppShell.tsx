import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  FileText,
  Home,
  ListChecks,
  Loader2,
  MessageCircle,
  Network,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { useHealth } from "@/api/endpoints/health";
import { Tooltip } from "@/components/ui/tooltip";
import { useChatStream } from "@/features/chat/ChatStreamProvider";
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
  const chat = useChatStream();
  return (
    <div className="flex h-full">
      <aside className="flex w-56 flex-col border-r border-zinc-200 bg-white">
        <div className="px-4 py-4 text-lg font-semibold">{env.VITE_APP_NAME}</div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            const isChat = item.to === "/chat";
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
                <span className="flex-1">{item.label}</span>
                {isChat && chat.busy ? (
                  <Tooltip content="Agent is working, click to view">
                    <span
                      className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700"
                      aria-label="Agent working"
                    >
                      <Loader2 className="h-2.5 w-2.5 animate-spin" />
                    </span>
                  </Tooltip>
                ) : isChat && chat.unseenCount > 0 ? (
                  <Tooltip
                    content={`${chat.unseenCount} new chat result${chat.unseenCount === 1 ? "" : "s"}`}
                  >
                    <span
                      className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-indigo-600 px-1 text-[10px] font-semibold text-white"
                      aria-label={`${chat.unseenCount} new chat results`}
                    >
                      {chat.unseenCount}
                    </span>
                  </Tooltip>
                ) : null}
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
