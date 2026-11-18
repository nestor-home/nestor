import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { AgentFigure } from "@/components/agent-figure";
import { Kbd } from "@/components/status";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AgentPresenceProvider, useAgentPresence } from "@/features/agent/presence";
import { RestartBanner } from "@/features/config/restart";
import { UpdateAvailable } from "@/features/system/updates";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAccountLocale, useT } from "@/i18n";
import { useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { AccountMenu } from "./account-menu";
import { useAttention } from "./attention";
import { CommandPalette, useCommandPalette } from "./command-palette";
import { useLive } from "./live";
import { destinations, inSpace, type Space, visibleSpaces } from "./nav";
import { useGoKeys } from "./use-go-keys";

/**
 * The frame: a night-ink rail with the agent and the few spaces of the household (a tab bar under the
 * thumb on a phone), settings apart at its foot, and ⌘K to jump anywhere.
 */
export function AppShell() {
  const t = useT();
  const me = useMe();
  // the chat fills the window and scrolls its own messages, as messaging apps do
  const bleed = useRouterState({ select: (s) => s.location.pathname.startsWith("/chat") });
  useAccountLocale(me.locale);
  const palette = useCommandPalette();
  useGoKeys(destinations(me.scopes));
  const search = () => palette.setOpen(() => true);
  const mobile = useIsMobile();

  return (
    <AgentPresenceProvider>
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("shell-skip")}
      </a>
      {mobile ? <TopBar onSearch={search} /> : <Rail onSearch={search} />}
      <main
        id="content"
        className={cn(
          "min-w-0 md:pl-[5.5rem]",
          bleed
            ? "flex h-[calc(100svh-3.5rem-4rem-env(safe-area-inset-bottom))] flex-col overflow-hidden md:h-svh"
            : "px-4 pt-5 pb-[calc(6rem+env(safe-area-inset-bottom))] sm:px-6 md:pt-8 md:pr-10 md:pb-16 md:pl-[calc(5.5rem+2.5rem)]",
        )}
      >
        {bleed ? (
          <Outlet />
        ) : (
          <div className="mx-auto max-w-[76rem]">
            <RestartBanner />
            <Outlet />
          </div>
        )}
      </main>
      {mobile ? <TabBar /> : null}
      <CommandPalette open={palette.open} onOpenChange={(open) => palette.setOpen(() => open)} />
    </AgentPresenceProvider>
  );
}

function useSpaces() {
  const me = useMe();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { spaces, settings } = visibleSpaces(me.scopes);
  const { items } = useAttention();
  return { spaces, settings, path, waiting: items.length };
}

/** From `md` up: the agent, the spaces as labelled pebbles, then search, settings and the account. */
function Rail({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  const { spaces, settings, path, waiting } = useSpaces();
  return (
    <aside className="rail fixed inset-y-0 left-0 z-40 flex w-[5.5rem] flex-col items-center gap-1 pt-5 pb-3">
      <AgentMark />
      <nav aria-label={t("shell-sections")} className="mt-6 grid w-full gap-1 px-2">
        {spaces.map((s) => (
          <SpaceLink key={s.to} space={s} here={inSpace(s, path)} badge={s.to === "/" ? waiting : 0} />
        ))}
      </nav>
      <div className="mt-auto grid w-full justify-items-center gap-1 px-2">
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                onClick={onSearch}
                aria-label={t("shell-go-to")}
                className="grid size-11 place-items-center rounded-xl text-ink-muted hover:bg-white/8 hover:text-ink"
              />
            }
          >
            <Search className="size-5" aria-hidden="true" />
          </TooltipTrigger>
          <TooltipContent side="right">
            {t("shell-go-to")} <Kbd>⌘K</Kbd>
          </TooltipContent>
        </Tooltip>
        {settings ? <SpaceLink space={settings} here={inSpace(settings, path)} badge={0} /> : null}
        <UpdateAvailable compact />
        <AccountMenu compact />
      </div>
    </aside>
  );
}

function SpaceLink({ space, here, badge }: { space: Space; here: boolean; badge: number }) {
  const t = useT();
  return (
    <Link
      to={space.to}
      aria-current={here ? "page" : undefined}
      className={cn(
        "group relative grid justify-items-center gap-1 rounded-xl px-1 py-2 text-[0.72rem] leading-tight font-medium transition-colors",
        here ? "text-ink" : "text-ink-muted hover:text-ink",
      )}
    >
      <span
        className={cn(
          "relative grid h-9 w-12 place-items-center rounded-full transition-colors",
          here ? "bg-[#f5f0e6] text-[#1d1913]" : "group-hover:bg-white/8",
        )}
      >
        <space.icon className="size-5" aria-hidden="true" />
        {badge ? (
          <span className="absolute -top-0.5 -right-0.5 grid min-w-4.5 place-items-center rounded-full bg-ember px-1 text-[0.68rem] leading-4.5 font-semibold text-on-ember tabular">
            {badge}
          </span>
        ) : null}
      </span>
      {t(space.label)}
    </Link>
  );
}

/** The agent at the head of the rail: its face follows what it does, its dot whether it is reachable. */
function AgentMark() {
  const t = useT();
  const me = useMe();
  const { status } = useLive();
  const { state: figure } = useAgentPresence();
  const online = status === "open";
  const state = t(
    online ? `home-state-${figure}` : status === "connecting" ? "shell-live-connecting" : "shell-agent-offline",
  );
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Link
            to="/"
            aria-label={t("shell-agent-label", { assistant: me.assistant, state })}
            className="relative grid size-12 place-items-center rounded-2xl hover:bg-white/8"
          />
        }
      >
        <AgentFigure state={figure} size="md" live />
        <span
          aria-hidden="true"
          className={cn(
            "absolute top-0.5 right-0.5 size-2.5 rounded-full ring-2 ring-[#0f0d0a]",
            online ? "live-dot bg-ember" : status === "connecting" ? "bg-amber" : "bg-ink-faint",
          )}
        />
      </TooltipTrigger>
      <TooltipContent side="right">
        {me.assistant} · {state}
      </TooltipContent>
    </Tooltip>
  );
}

/** On a phone: the agent's name, search and the account along the top. */
function TopBar({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  const me = useMe();
  const { state: figure } = useAgentPresence();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 bg-paper/92 px-3 pt-[env(safe-area-inset-top)] backdrop-blur-sm">
      <Link
        to="/"
        aria-label={t("shell-home-link", { assistant: me.assistant })}
        className="flex items-center gap-2 px-1"
      >
        <AgentFigure state={figure} size="sm" />
        <span className="font-serif text-[1.35rem] leading-none text-ink">{me.assistant}</span>
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          onClick={onSearch}
          aria-label={t("shell-go-to")}
          className="grid size-11 place-items-center rounded-xl text-ink-muted"
        >
          <Search className="size-5" aria-hidden="true" />
        </button>
        <AccountMenu compact />
      </div>
    </header>
  );
}

/** On a phone: the spaces under the thumb. */
function TabBar() {
  const t = useT();
  const { spaces, settings, path, waiting } = useSpaces();
  const all = settings ? [...spaces, settings] : spaces;
  return (
    <nav
      aria-label={t("shell-sections")}
      className="rail fixed inset-x-0 bottom-0 z-40 flex justify-around px-1 pt-1.5 pb-[calc(0.375rem+env(safe-area-inset-bottom))]"
    >
      {all.map((s) => (
        <SpaceLink key={s.to} space={s} here={inSpace(s, path)} badge={s.to === "/" ? waiting : 0} />
      ))}
    </nav>
  );
}
