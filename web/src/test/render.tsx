import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { type JournalItem, type JournalStream, type LiveStatus, setCsrfToken } from "@/api";
import { NoticeProvider } from "@/components/notices";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/i18n";
import { ThemeProvider } from "@/lib/theme";
import { CSRF } from "@/mocks/handlers";
import { createAppRouter } from "@/router";

/** A journal stream the test drives by hand. */
export function fakeStream() {
  let deliver: ((item: JournalItem) => void) | undefined;
  let report: ((status: LiveStatus) => void) | undefined;
  const stream: JournalStream & { emit: (item: JournalItem) => void; status: (s: LiveStatus) => void } = {
    subscribe(onItem, onStatus) {
      deliver = onItem;
      report = onStatus;
      onStatus("open");
      return () => {
        deliver = undefined;
      };
    },
    emit: (item) => act(() => deliver?.(item)),
    status: (s) => act(() => report?.(s)),
  };
  return stream;
}

export function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

/** The whole admin at `path`, on the mock API, with a hand-driven live stream. */
export function renderApp(path: string) {
  const stream = fakeStream();
  const queryClient = testQueryClient();
  const router = createAppRouter({ queryClient, stream }, createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <TooltipProvider>
            <NoticeProvider>
              <RouterProvider router={router} />
            </NoticeProvider>
          </TooltipProvider>
        </I18nProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...view, router, stream, queryClient };
}

/** One component with the providers it needs, outside the router, as a signed-in owner. */
export function renderWithProviders(ui: ReactNode) {
  setCsrfToken(CSRF);
  const queryClient = testQueryClient();
  return {
    queryClient,
    ...render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <I18nProvider>
            <NoticeProvider>{ui}</NoticeProvider>
          </I18nProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    ),
  };
}

export function liveItem(overrides: Partial<JournalItem> = {}): JournalItem {
  return {
    id: String(100_000 + Math.floor(Math.random() * 900_000)),
    uid: `live-${Math.random().toString(36).slice(2)}`,
    kind_label: "Conversations",
    at: new Date().toISOString(),
    type: "conversation.user_turn",
    kind: "conversation",
    message: { id: "journal-user-said", args: { name: "Jules" } },
    text: "Jules a dit",
    detail: "",
    reason: null,
    people: ["jules"],
    channels: ["voice"],
    room: null,
    tone: "normal",
    links: {},
    cause: null,
    outcome: null,
    tool: null,
    brand: "voice",
    ...overrides,
  };
}

/** Waits, inside act(), until no query is fetching: what a person sees once the page has loaded. */
export async function settle(queryClient: QueryClient, limitMs = 4000): Promise<void> {
  const until = Date.now() + limitMs;
  do {
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
  } while ((queryClient.isFetching() > 0 || queryClient.isMutating() > 0) && Date.now() < until);
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
}
