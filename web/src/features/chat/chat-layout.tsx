/**
 * Talk: the discussions beside the open one on a wide screen. On a phone they are two levels: the list with a
 * composer to start a new one, then the discussion with a way back. ⇧⌘O starts a new one from anywhere in it.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { Search, SquarePen } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { type Chat, chatsQuery, keys } from "@/api";
import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page";
import { Failure, Loading, Notice } from "@/components/states";
import { Kbd, Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLiveItems } from "@/features/shell/live";
import { useIsMobile } from "@/hooks/use-mobile";
import { useT } from "@/i18n";
import { daysBefore, moment } from "@/lib/dates";
import { cn } from "@/lib/utils";

const WEB_CHANNEL = "channels:\n  - kind: web"; // what turns the chat on, in the configuration

export function ChatLayout() {
  const t = useT();
  const navigate = useNavigate();
  const mobile = useIsMobile();
  const chats = useQuery(chatsQuery);
  const queryClient = useQueryClient();
  const sessions = chats.data?.sessions;

  useLiveItems((item) => {
    if (sessions && item.kind === "conversation" && item.links.session?.startsWith(sessions)) {
      void queryClient.invalidateQueries({ queryKey: keys.chats, exact: true });
    }
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "o" && event.shiftKey && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        void navigate({ to: "/chat" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (chats.error instanceof ApiError && ["chat_off", "chat_needs_person"].includes(chats.error.code)) {
    return (
      <div className="mx-auto w-full max-w-xl px-4 pt-8 md:pt-16">
        <PageHeader title={t("chat-title")} />
        <Notice tone="attention">
          <p>{chats.error.message}</p>
          {chats.error.code === "chat_off" ? <pre className="code-block mt-3">{WEB_CHANNEL}</pre> : null}
        </Notice>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {mobile ? null : (
        <aside className="flex w-80 shrink-0 flex-col bg-paper-sunken/50" aria-label={t("chat-list")}>
          <ChatList
            lead={
              <div className="flex items-center justify-between gap-2 px-5 pt-6 pb-3">
                <h2 className="display-3 text-ink">{t("chat-list")}</h2>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="outline"
                        size="icon"
                        className="rounded-full bg-paper-raised"
                        nativeButton={false}
                        aria-label={t("chat-new")}
                        aria-keyshortcuts="Meta+Shift+O"
                        render={<Link to="/chat" />}
                      />
                    }
                  >
                    <SquarePen />
                  </TooltipTrigger>
                  <TooltipContent>
                    {t("chat-new")} · <Kbd>⇧⌘O</Kbd>
                  </TooltipContent>
                </Tooltip>
              </div>
            }
          />
        </aside>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}

/** Today, yesterday, this week, this month, before: the groups of the list, by the chat's last message. */
function groupOf(iso: string, now: Date): string {
  const days = daysBefore(iso, now);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return "week";
  if (days < 30) return "month";
  return "older";
}

/** The discussions, latest first, found by their words; `lead` is what stands above them. */
export function ChatList({ lead }: { lead: ReactNode }) {
  const t = useT();
  const { data, isPending: loading, error, refetch: retry } = useQuery(chatsQuery);
  const chats = data?.chats;
  const { chat: open } = useParams({ strict: false });
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const words = query.trim().toLocaleLowerCase();
    const now = new Date();
    const found = new Map<string, Chat[]>();
    for (const chat of chats ?? []) {
      if (words && !titleOf(chat, t).toLocaleLowerCase().includes(words)) continue;
      const group = groupOf(chat.updated_at, now);
      found.set(group, [...(found.get(group) ?? []), chat]);
    }
    return [...found];
  }, [chats, query, t]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {lead}
      <search className="px-4 pb-2">
        <InputGroup className="h-10 rounded-full border-transparent px-1 shadow-(--lift)">
          <InputGroupAddon>
            <Search aria-hidden="true" />
          </InputGroupAddon>
          <InputGroupInput
            type="search"
            aria-label={t("chat-search")}
            placeholder={t("chat-search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </InputGroup>
      </search>
      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-6" aria-label={t("chat-list")}>
        {loading ? (
          <div className="px-1 pt-2">
            <Loading lines={4} />
          </div>
        ) : error ? (
          <Failure error={error} retry={retry} className="mx-1 mt-2" />
        ) : !groups.length ? (
          <p className="px-2 py-3 text-body text-ink-muted">{t(query ? "chat-search-none" : "chat-none")}</p>
        ) : (
          groups.map(([group, items]) => (
            <section key={group} className="mt-4 first:mt-2">
              <h3 className="caption px-2 pb-1.5">{t(`chat-group-${group}`)}</h3>
              <ul className="grid gap-1">
                {items.map((chat) => (
                  <li key={chat.id}>
                    <Link
                      to="/chat/$chat"
                      params={{ chat: chat.id }}
                      aria-current={chat.id === open ? "page" : undefined}
                      className={cn(
                        "flex min-h-12 items-center gap-3 px-3 py-2",
                        chat.id === open ? "surface" : "rounded-(--radius-surface) hover:bg-paper-sunken",
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-body font-medium text-ink">{titleOf(chat, t)}</span>
                        <span className="block text-meta text-ink-muted">{moment(chat.updated_at)}</span>
                      </span>
                      {chat.answering ? (
                        <Status tone="accent" className="shrink-0">
                          {t("chat-answering")}
                        </Status>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </nav>
    </div>
  );
}

/** A chat's name: its first words, or what its first message carried. */
export function titleOf(chat: Chat, t: (id: string, args?: Record<string, string | number>) => string): string {
  if (chat.title) return chat.title;
  const kind = chat.files[0];
  return kind ? t(`chat-file-${kind}`) : t("chat-new");
}
