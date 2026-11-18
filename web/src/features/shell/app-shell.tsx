import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useEffect } from "react";
import { AgentFigure } from "@/components/agent-figure";
import { Kbd } from "@/components/status";
import { AgentPresenceProvider, useAgentPresence } from "@/features/agent/presence";
import { RestartBanner } from "@/features/config/restart";
import { UpdateAvailable } from "@/features/system/updates";
import { useIsMobile, useRail } from "@/hooks/use-mobile";
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
  const rail = useRail();

  return (
    <AgentPresenceProvider>
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("shell-skip")}
      </a>
      {mobile ? <TopBar onSearch={search} /> : <Rail onSearch={search} rail={rail} />}
      <main
        id="content"
        data-rail={rail.wide ? "wide" : "narrow"}
        className={cn(
          "min-w-0 md:pl-[4.75rem] md:wide:pl-64 md:transition-[padding] md:duration-200",
          bleed
            ? "flex h-[calc(100svh-3.5rem-4rem-env(safe-area-inset-bottom))] flex-col overflow-hidden md:h-svh"
            : "px-4 pt-5 pb-[calc(6rem+env(safe-area-inset-bottom))] sm:px-6 md:pt-8 md:pr-10 md:pb-16 md:pl-[calc(4.75rem+2.5rem)] md:wide:pl-[calc(16rem+3rem)]",
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

/**
 * From `md` up: the agent and its state, the way to jump anywhere, the spaces, then settings and the account.
 * Icons alone until `lg`, where each takes its name beside it.
 */
function Rail({ onSearch, rail }: { onSearch: () => void; rail: ReturnType<typeof useRail> }) {
  const t = useT();
  const { spaces, settings, path, waiting } = useSpaces();
  const { toggle, roomy } = rail;
  // `[` folds and unfolds it, as ⌘B does, unless one is typing
  useEffect(() => {
    if (!roomy) return;
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return;
      const chord = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b";
      if (!chord && (event.key !== "[" || event.metaKey || event.ctrlKey || event.altKey)) return;
      event.preventDefault();
      toggle();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [roomy, toggle]);
  const fold = t(rail.wide ? "shell-rail-fold" : "shell-rail-unfold");
  return (
    <div
      data-rail={rail.wide ? "wide" : "narrow"}
      className="rail fixed inset-y-0 left-0 z-40 flex w-[4.75rem] flex-col gap-4 px-3 pt-5 pb-3 wide:w-64 wide:px-4 transition-[width] duration-200"
    >
      <div className="flex items-center gap-1 narrow:flex-col">
        <div className="min-w-0 flex-1 narrow:flex-none">
          <AgentMark />
        </div>
        {roomy ? (
          <button
            type="button"
            onClick={toggle}
            title={`${fold} · [`}
            aria-label={fold}
            aria-expanded={rail.wide}
            aria-keyshortcuts="Meta+B ["
            className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-white/8 hover:text-ink"
          >
            {rail.wide ? (
              <PanelLeftClose className="size-4.5" aria-hidden="true" />
            ) : (
              <PanelLeftOpen className="size-4.5" aria-hidden="true" />
            )}
          </button>
        ) : null}
      </div>
      <button
        type="button"
        onClick={onSearch}
        title={t("shell-go-to")}
        className="flex h-10 items-center gap-2.5 rounded-xl bg-white/6 px-3 text-body text-ink-muted transition-colors hover:bg-white/10 hover:text-ink narrow:justify-center narrow:px-0"
      >
        <Search className="size-4.5 shrink-0" aria-hidden="true" />
        <span className="narrow:sr-only">{t("shell-go-to")}</span>
        <span className="ml-auto narrow:hidden">
          <Kbd>⌘K</Kbd>
        </span>
      </button>
      <nav aria-label={t("shell-sections")} className="flex min-h-0 flex-1 flex-col gap-1">
        {spaces.map((s) => (
          <RailLink key={s.to} space={s} here={inSpace(s, path)} badge={s.to === "/" ? waiting : 0} />
        ))}
        {settings ? (
          <div className="mt-auto grid">
            <RailLink space={settings} here={inSpace(settings, path)} badge={0} />
          </div>
        ) : null}
      </nav>
      <div className="flex items-center gap-1 border-t border-white/8 pt-3 narrow:flex-col">
        <div className="min-w-0 flex-1 narrow:flex-none">
          <AccountMenu compact="narrow" />
        </div>
        <UpdateAvailable compact />
      </div>
    </div>
  );
}

/** A space in the rail: its icon, its name from `lg`, and what waits there. */
function RailLink({ space, here, badge }: { space: Space; here: boolean; badge: number }) {
  const t = useT();
  return (
    <Link
      to={space.to}
      title={t(space.label)}
      aria-current={here ? "page" : undefined}
      aria-label={badge ? t("shell-space-waiting", { space: t(space.label), count: badge }) : undefined}
      className={cn(
        "relative flex h-11 items-center gap-3 rounded-xl px-3 text-body font-medium transition-colors narrow:justify-center narrow:px-0",
        here ? "bg-day-paper text-day-ink" : "text-ink-muted hover:bg-white/8 hover:text-ink",
      )}
    >
      <space.icon className="size-5 shrink-0" aria-hidden="true" />
      <span className="narrow:sr-only">{t(space.label)}</span>
      {badge ? (
        <span className="ml-auto grid min-w-5 place-items-center rounded-full bg-ember px-1.5 text-micro leading-5 font-semibold text-on-ember tabular narrow:absolute narrow:-top-1 narrow:-right-1">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

/** A space in the phone's tab bar: its icon over its name. */
function SpaceLink({ space, here, badge }: { space: Space; here: boolean; badge: number }) {
  const t = useT();
  return (
    <Link
      to={space.to}
      aria-current={here ? "page" : undefined}
      aria-label={badge ? t("shell-space-waiting", { space: t(space.label), count: badge }) : undefined}
      className={cn(
        "group relative grid justify-items-center gap-1 rounded-xl px-1 py-2 text-micro leading-tight font-medium transition-colors",
        here ? "text-ink" : "text-ink-muted hover:text-ink",
      )}
    >
      <span
        className={cn(
          "relative grid h-9 w-12 place-items-center rounded-full transition-colors",
          here ? "bg-day-paper text-day-ink" : "group-hover:bg-white/8",
        )}
      >
        <space.icon className="size-5" aria-hidden="true" />
        {badge ? (
          <span className="absolute -top-0.5 -right-0.5 grid min-w-4.5 place-items-center rounded-full bg-ember px-1 text-micro leading-4.5 font-semibold text-on-ember tabular">
            {badge}
          </span>
        ) : null}
      </span>
      {t(space.label)}
    </Link>
  );
}

/** The agent at the head of the rail: its face follows what it does, its name and state beside it from `lg`. */
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
    <Link
      to="/"
      title={`${me.assistant} · ${state}`}
      aria-label={t("shell-agent-label", { assistant: me.assistant, state })}
      className="flex items-center gap-3 rounded-2xl p-1 hover:bg-white/6 narrow:justify-center"
    >
      <span className="relative shrink-0">
        <AgentFigure state={figure} size="md" live />
        <span
          aria-hidden="true"
          className={cn(
            "absolute -top-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-night wide:hidden",
            online ? "live-dot bg-ember" : status === "connecting" ? "bg-amber" : "bg-ink-faint",
          )}
        />
      </span>
      <span className="min-w-0 narrow:hidden">
        <span className="block truncate title-card text-ink">{me.assistant}</span>
        <span className="mt-1.5 flex items-center gap-1.5 text-meta text-ink-muted">
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              online ? "live-dot bg-ember" : status === "connecting" ? "bg-amber" : "bg-ink-faint",
            )}
          />
          <span className="truncate">{state}</span>
        </span>
      </span>
    </Link>
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
        <span className="title-card text-ink">{me.assistant}</span>
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
