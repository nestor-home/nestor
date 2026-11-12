/**
 * The chat: its list of chats beside the open one, as messaging apps lay it out. Below `lg`, the list opens as a
 * sheet. ⇧⌘O starts a new chat from anywhere in it.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { Search, SquarePen } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { type Chat, chatsQuery, keys } from "@/api";
import { ApiError } from "@/api/client";
import { Failure, Loading, Notice } from "@/components/states";
import { Kbd } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLiveItems } from "@/features/shell/live";
import { useT } from "@/i18n";
import { hourMinute } from "@/lib/dates";
import { cn } from "@/lib/utils";

const WEB_CHANNEL = "channels:\n  - kind: web"; // what turns the chat on, in the configuration

export function ChatLayout() {
  const t = useT();
  const navigate = useNavigate();
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
      <div className="mx-auto max-w-xl px-4 pt-16">
        <h1 className="display-2 text-ink">{t("chat-title")}</h1>
        <Notice tone="attention" className="mt-6">
          <p>{chats.error.message}</p>
          {chats.error.code === "chat_off" ? (
            <pre className="mt-3 rounded-md bg-paper-sunken px-3 py-2 font-mono text-[0.8rem]">{WEB_CHANNEL}</pre>
          ) : null}
        </Notice>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-rule lg:flex" aria-label={t("chat-list")}>
        <ChatList chats={chats.data?.chats} loading={chats.isPending} error={chats.error} retry={chats.refetch} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}

const DAY = 86_400_000;

/** Today, yesterday, this week, this month, before: the groups of the list, by the chat's last message. */
function groupOf(iso: string, now: Date): string {
  const midnight = new Date(now);
  midnight.setHours(0, 0, 0, 0);
  const at = new Date(iso).getTime();
  if (at >= midnight.getTime()) return "today";
  if (at >= midnight.getTime() - DAY) return "yesterday";
  if (at >= midnight.getTime() - 6 * DAY) return "week";
  if (at >= midnight.getTime() - 29 * DAY) return "month";
  return "older";
}

export function ChatList({
  chats,
  loading,
  error,
  retry,
  onNavigate,
}: {
  chats: Chat[] | undefined;
  loading: boolean;
  error: unknown;
  retry: () => void;
  onNavigate?: () => void;
}) {
  const t = useT();
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
      <div className="flex items-center justify-between gap-2 px-4 pt-5 pb-3">
        <h2 className="font-serif text-[1.35rem] leading-none text-ink">{t("chat-title")}</h2>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("chat-new")}
                aria-keyshortcuts="Meta+Shift+O"
                render={<Link to="/chat" onClick={onNavigate} />}
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
      <div className="px-3 pb-2">
        <label className="flex h-8 items-center gap-2 rounded-md border border-rule bg-paper-raised px-2.5 focus-within:border-ink">
          <Search className="size-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
          <span className="sr-only">{t("chat-search")}</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("chat-search")}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
      </div>
      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-6" aria-label={t("chat-list")}>
        {loading ? (
          <div className="px-2">
            <Loading lines={4} />
          </div>
        ) : error ? (
          <Failure error={error} retry={retry} className="mx-2" />
        ) : !groups.length ? (
          <p className="px-2.5 py-3 text-sm text-ink-muted">{t(query ? "chat-search-none" : "chat-none")}</p>
        ) : (
          groups.map(([group, items]) => (
            <section key={group} className="mt-3 first:mt-1">
              <h3 className="label-mono px-2.5 pb-1 text-[0.68rem] text-ink-faint">{t(`chat-group-${group}`)}</h3>
              <ul className="grid gap-px">
                {items.map((chat) => (
                  <li key={chat.id}>
                    <Link
                      to="/chat/$chat"
                      params={{ chat: chat.id }}
                      onClick={onNavigate}
                      aria-current={chat.id === open ? "page" : undefined}
                      className={cn(
                        "flex h-9 items-center gap-2 rounded-md px-2.5 text-sm text-ink-muted hover:bg-paper-sunken hover:text-ink pointer-coarse:h-11",
                        chat.id === open && "bg-paper-sunken text-ink",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">{titleOf(chat, t)}</span>
                      {chat.answering ? (
                        <span className="flex shrink-0 items-center">
                          <span className="live-dot size-1.5 rounded-full bg-ember" aria-hidden="true" />
                          <span className="sr-only">{t("chat-answering")}</span>
                        </span>
                      ) : (
                        <span className="shrink-0 font-mono text-[0.7rem] text-ink-faint">
                          {group === "today" ? hourMinute(chat.updated_at) : null}
                        </span>
                      )}
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
  return kind ? t(`chat-file-${kind}`) : t("chat-untitled");
}
