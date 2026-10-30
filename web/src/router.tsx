import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { ApiError, eventSourceStream, type JournalStream } from "@/api";
import { routeTree } from "./routeTree.gen";

export interface RouterContext {
  queryClient: QueryClient;
  stream: JournalStream;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: true,
        // a refusal will not change by asking again; a network hiccup may
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
}

export function createAppRouter(
  context: Partial<RouterContext> = {},
  history?: Parameters<typeof createRouter>[0]["history"],
) {
  return createRouter({
    routeTree,
    context: { queryClient: context.queryClient ?? createQueryClient(), stream: context.stream ?? eventSourceStream },
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0, // TanStack Query owns caching
    scrollRestoration: true,
    ...(history ? { history } : {}),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
