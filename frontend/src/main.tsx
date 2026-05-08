import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "sonner";

import { ThemeProvider, useTheme } from "@/components/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { queryClient } from "@/lib/query-client";
import "@/styles/globals.css";

import { routeTree } from "./routeTree.gen";

const router = createRouter({ routeTree, context: { queryClient } });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster position="bottom-right" richColors closeButton theme={resolvedTheme} />
  );
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={150} skipDelayDuration={300}>
          <RouterProvider router={router} />
          <ThemedToaster />
          {import.meta.env.DEV ? <ReactQueryDevtools initialIsOpen={false} /> : null}
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
