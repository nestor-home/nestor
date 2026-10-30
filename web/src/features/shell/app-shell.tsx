import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { PanelLeft, Search } from "lucide-react";
import { Kbd } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Wordmark } from "@/components/wordmark";
import { useAccountLocale, useT } from "@/i18n";
import { useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { AccountMenu } from "./account-menu";
import { CommandPalette, useCommandPalette } from "./command-palette";
import { useLive } from "./live";
import { LiveIndicator } from "./live-indicator";
import { flatNav, type NavItem, visibleNav } from "./nav";
import { Ticker } from "./ticker";
import { useGoKeys } from "./use-go-keys";

function isHere(item: NavItem, path: string): boolean {
  if (item.to === "/") return path === "/";
  return path === item.to || path.startsWith(`${item.to}/`);
}

/**
 * The frame: shadcn's Sidebar, collapsible to an icon rail (⌘B or `[`, remembered), a sheet
 * below `md` opened from the top bar; the mono status line above every screen.
 */
export function AppShell() {
  const t = useT();
  const me = useMe();
  useAccountLocale(me.locale);
  const palette = useCommandPalette();
  useGoKeys(flatNav(me.scopes));

  return (
    <SidebarProvider>
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("shell-skip")}
      </a>
      <Navigation />
      <SidebarInset className="min-w-0 bg-paper">
        <MobileBar onSearch={() => palette.setOpen(() => true)} />
        <Ticker onSearch={() => palette.setOpen(() => true)} />
        <div
          id="content"
          className="min-w-0 px-4 pt-8 pb-[calc(4rem+env(safe-area-inset-bottom))] sm:px-6 md:px-10 md:pt-10 lg:px-14"
        >
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </div>
      </SidebarInset>
      <CommandPalette open={palette.open} onOpenChange={(open) => palette.setOpen(() => open)} />
    </SidebarProvider>
  );
}

function Navigation() {
  const t = useT();
  const me = useMe();
  const groups = visibleNav(me.scopes);
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { state, setOpenMobile, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  return (
    <Sidebar collapsible="icon" className="border-rule">
      <SidebarHeader className="px-4 pt-6 pb-4 group-data-[collapsible=icon]:px-2">
        <AgentHeader collapsed={collapsed} onNavigate={() => setOpenMobile(false)} />
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label={t("shell-sections")}>
          {groups.map((group) => (
            <SidebarGroup key={group.label ?? "main"} className="py-1.5">
              {group.label ? (
                <SidebarGroupLabel className="label-mono h-6 px-2.5 text-[0.68rem]">{t(group.label)}</SidebarGroupLabel>
              ) : null}
              <SidebarGroupContent>
                <SidebarMenu className="gap-px">
                  {group.items.map((item) => {
                    const here = isHere(item, path);
                    return (
                      <SidebarMenuItem key={item.to}>
                        <SidebarMenuButton
                          isActive={here}
                          tooltip={`${t(item.label)} · g ${item.key}`}
                          className="group/nav h-9 justify-between text-ink-muted data-active:text-ink pointer-coarse:h-11"
                          render={
                            <Link
                              to={item.to}
                              aria-current={here ? "page" : undefined}
                              onClick={() => setOpenMobile(false)}
                            />
                          }
                        >
                          <span className="flex items-center gap-2.5">
                            <item.icon
                              className={cn("size-4", here ? "text-ember" : "text-ink-faint")}
                              aria-hidden="true"
                            />
                            <span className="group-data-[collapsible=icon]:sr-only">{t(item.label)}</span>
                          </span>
                          <span
                            aria-hidden="true"
                            className="hidden gap-0.5 opacity-0 transition-opacity group-hover/nav:opacity-100 md:inline-flex group-data-[collapsible=icon]:hidden"
                          >
                            <Kbd>g</Kbd>
                            <Kbd>{item.key}</Kbd>
                          </span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter className="gap-2 border-t border-rule px-2 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
        <AccountMenu compact={collapsed} />
        <CollapseToggle />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

/**
 * The agent first, the software second: the instance's name ("Richie", "Alfred"…) in the display
 * serif with its live state, and the nestor mark small beneath. Collapsed: the initial and the dot.
 */
function AgentHeader({ collapsed, onNavigate }: { collapsed: boolean; onNavigate: () => void }) {
  const t = useT();
  const me = useMe();
  const { status } = useLive();
  const online = status === "open";
  const state = t(
    online ? "shell-agent-online" : status === "connecting" ? "shell-live-connecting" : "shell-agent-offline",
  );
  const dot = (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        online ? "live-dot bg-ember" : status === "connecting" ? "bg-amber" : "border border-ink-faint",
      )}
    />
  );
  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <Link
              to="/"
              onClick={onNavigate}
              aria-label={t("shell-agent-label", { assistant: me.assistant, state })}
              className="relative mx-auto grid size-9 place-items-center rounded-md font-serif text-xl text-ink hover:bg-paper-sunken"
            />
          }
        >
          {me.assistant.slice(0, 1).toUpperCase()}
          <span className="absolute top-1 right-1">{dot}</span>
        </TooltipTrigger>
        <TooltipContent side="right">
          {me.assistant} · {state}
        </TooltipContent>
      </Tooltip>
    );
  }
  return (
    <div>
      <Link
        to="/"
        onClick={onNavigate}
        aria-label={t("shell-agent-label", { assistant: me.assistant, state })}
        className="block rounded-sm"
      >
        <span className="block font-serif text-[1.75rem] leading-none text-ink [font-variation-settings:'SOFT'_100,'opsz'_72]">
          {me.assistant}
        </span>
      </Link>
      <p className="mt-2 flex items-center gap-2 font-mono text-[0.7rem] text-ink-muted" aria-live="polite">
        {dot}
        {state}
      </p>
      <p className="mt-4 flex items-center gap-1.5 text-ink-faint">
        <Wordmark className="text-[0.95rem] text-ink-muted" />
      </p>
    </div>
  );
}

/** Collapse to the icon rail and back; the shortcut is in the tooltip and the label. */
function CollapseToggle() {
  const t = useT();
  const { state, toggleSidebar, isMobile } = useSidebar();
  if (isMobile) return null;
  const label = t(state === "expanded" ? "shell-sidebar-collapse" : "shell-sidebar-expand");
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleSidebar}
            aria-expanded={state === "expanded"}
            aria-keyshortcuts="Meta+B ["
            className="justify-start gap-2.5 px-2.5 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          />
        }
      >
        <PanelLeft aria-hidden="true" />
        <span className="group-data-[collapsible=icon]:sr-only">{label}</span>
      </TooltipTrigger>
      <TooltipContent side="right">
        {label} · <Kbd>⌘B</Kbd> <Kbd>[</Kbd>
      </TooltipContent>
    </Tooltip>
  );
}

/** Below `md`: the top bar opens the navigation sheet and keeps the essentials at hand. */
function MobileBar({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  const me = useMe();
  const { toggleSidebar, isMobile } = useSidebar();
  if (!isMobile) return null;
  return (
    <div className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-rule bg-paper/95 px-2 pt-[env(safe-area-inset-top)] backdrop-blur-[2px] md:hidden">
      <Button variant="ghost" size="icon-lg" onClick={toggleSidebar} aria-label={t("shell-open-menu")}>
        <PanelLeft />
      </Button>
      <Link to="/" aria-label={t("shell-home-link", { assistant: me.assistant })} className="rounded-sm px-1">
        <span className="font-serif text-[1.35rem] leading-none text-ink">{me.assistant}</span>
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <LiveIndicator compact />
        <Button variant="ghost" size="icon-lg" onClick={onSearch} aria-label={t("shell-go-to")}>
          <Search />
        </Button>
        <AccountMenu compact />
      </div>
    </div>
  );
}
