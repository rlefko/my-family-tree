import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/AppShell";
import { ChatStreamProvider } from "@/features/chat/ChatStreamProvider";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: () => (
    // Provider lives INSIDE the router so it can subscribe to route state,
    // but ABOVE every page so navigating between routes doesn't unmount the
    // chat-stream state and abort the in-flight SSE connection.
    <ChatStreamProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </ChatStreamProvider>
  ),
});
