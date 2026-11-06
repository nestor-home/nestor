import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, render } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  type AgentActivity,
  type EventLinks,
  type JournalItem,
  type JournalStream,
  type LiveStatus,
  setCsrfToken,
} from "@/api";
import { NoticeProvider } from "@/components/notices";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/i18n";
import { DEFAULT_LOCALE } from "@/i18n/catalog";
import { fetchCatalogue } from "@/i18n/provider";
import { ThemeProvider } from "@/lib/theme";
import { CSRF } from "@/mocks/handlers";
import { toItem } from "@/mocks/messages";
import { createAppRouter } from "@/router";

/** A journal stream the test drives by hand. */
export function fakeStream() {
  let deliver: ((item: JournalItem) => void) | undefined;
  let report: ((status: LiveStatus) => void) | undefined;
  let tell: ((activity: AgentActivity) => void) | undefined;
  const stream: JournalStream & {
    emit: (item: JournalItem) => void;
    status: (s: LiveStatus) => void;
    activity: (a: AgentActivity) => void;
  } = {
    subscribe(onItem, onStatus, onActivity) {
      deliver = onItem;
      report = onStatus;
      tell = onActivity;
      onStatus("open");
      return () => {
        deliver = undefined;
      };
    },
    emit: (item) => act(() => deliver?.(item)),
    status: (s) => act(() => report?.(s)),
    activity: (a) => act(() => tell?.(a)),
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
/** Renders `ui` with the app's providers, once the server's catalogue has arrived (as the app shows it). */
export async function renderWithProviders(ui: ReactNode) {
  setCsrfToken(CSRF);
  const queryClient = testQueryClient();
  const rendered = {
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
  await act(async () => {
    await fetchCatalogue(DEFAULT_LOCALE);
  });
  return rendered;
}

/** The English line the mock journal writes for an event type (`mocks/messages.ts` reads it as the server's message). */
const TITLE_OF: Record<string, string> = {
  "conversation.turn.user": "Jules said",
  "conversation.turn.assistant": "Richie answered",
  "conversation.turn.cut": "Answer cut off",
  "conversation.fallback": "Fallback answer: model too slow",
  "agent.tool.called": "Tool weather called",
  "agent.tool.completed": "Tool weather finished in 1.2 s",
  "task.started": "Task T handed to hermes",
  "task.progress": "Task T: new step",
  "task.ended": "Task T completed (2 min)",
  "watch.created": "Watch created: the parcel",
  "watch.triggered": "Watch w1 triggered by “Your parcel has shipped”",
  "initiative.considered": "Decided to speak to jules: watch w1",
  "initiative.delivered": "Message passed on: watch w1",
  "initiative.undeliverable": "Message not passed on: watch w1",
  "presence.changed": "Jules is in the kitchen",
  "observation.person.detected": "1 person seen by reachy (room “salon”)",
};

let livePosition = 100_000;

/** A journal item as the stream sends it, built as the mock server builds its own; `links` lists only the ones
 * the test cares about. */
export function liveItem({
  links,
  ...overrides
}: Partial<Omit<JournalItem, "links">> & { links?: Partial<EventLinks> } = {}): JournalItem {
  const type = overrides.type ?? "conversation.turn.user";
  const item = toItem(
    { type, title: TITLE_OF[type] ?? type, people: [{ id: "jules", name: "Jules" }], channels: ["voice"], links },
    { position: ++livePosition, id: `live-${Math.random().toString(36).slice(2)}`, at: new Date().toISOString() },
  );
  return { ...item, ...overrides, detail_text: overrides.detail_text ?? overrides.detail ?? item.detail_text };
}

/** Waits, inside act(), until no query is fetching: what a person sees once the page has loaded. */
export async function settle(queryClient: QueryClient, limitMs = 4000): Promise<void> {
  const until = Date.now() + limitMs;
  do {
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
  } while ((queryClient.isFetching() > 0 || queryClient.isMutating() > 0) && Date.now() < until);
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
}
