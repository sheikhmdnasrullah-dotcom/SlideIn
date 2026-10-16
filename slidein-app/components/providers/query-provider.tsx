"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/workspace/tooltip";
import { ApiRequestError } from "@/lib/api/errors";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Never retry a 4xx: the reason is already in the envelope.
              if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) {
                return false;
              }
              return failureCount < 1;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <NuqsAdapter>
        <TooltipProvider>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              classNames: {
                toast: "!bg-surface !text-ink-strong !ring-1 !ring-rule-strong !rounded-md",
                description: "!text-ink-faint",
              },
            }}
          />
        </TooltipProvider>
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
