import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { satellitesQuery, systemQuery, tasksQuery, watchesQuery } from "@/api";
import { Kbd } from "@/components/status";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";
import { useAttention } from "./attention";

/**
 * The signature status line along the top of every screen, in mono like a terminal's: the live
 * stream, what runs, what needs a look, and the way to jump anywhere (⌘K).
 */
export function Ticker({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  const canTasks = useCan("tasks:read");
  const canWatches = useCan("watches:read");
  const canSatellites = useCan("satellites:read");
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const watches = useQuery({ ...watchesQuery, enabled: canWatches });
  const satellites = useQuery({ ...satellitesQuery, enabled: canSatellites });
  const system = useQuery({ ...systemQuery, enabled: canSatellites });
  const { items } = useAttention();
  const paired = satellites.data?.paired ?? [];
  const online = paired.filter((s) => s.connected).length;
  return (
    <div className="sticky top-0 z-20 hidden h-10 items-center gap-4 border-b border-rule bg-paper/95 px-4 font-mono text-[0.7rem] text-ink-muted backdrop-blur-[2px] sm:px-6 md:flex md:px-10 lg:px-14">
      <p className="flex min-w-0 flex-1 items-center gap-4 overflow-hidden whitespace-nowrap">
        {tasks.data ? (
          <Link to="/tasks" className="hover:text-ink">
            {t("shell-ticker-tasks", { count: tasks.data.running.length })}
          </Link>
        ) : null}
        {watches.data ? (
          <Link to="/watches" className="hidden hover:text-ink sm:inline">
            {t("shell-ticker-watches", { count: watches.data.watches.length })}
          </Link>
        ) : null}
        {satellites.data ? (
          <Link to="/satellites" className="hidden hover:text-ink sm:inline">
            {t("shell-ticker-satellites", { online, total: paired.length })}
          </Link>
        ) : null}
        {items.length ? (
          <Link to="/" className="text-amber hover:underline">
            {t("shell-ticker-attention", { count: items.length })}
          </Link>
        ) : null}
      </p>
      {system.data ? (
        <span className="hidden text-ink-faint lg:inline">
          {t("shell-version", { version: system.data.nestor.version })}
        </span>
      ) : null}
      <button
        type="button"
        onClick={onSearch}
        className="inline-flex items-center gap-2 rounded-sm border border-rule px-2 py-1 text-ink-muted hover:border-rule-strong hover:text-ink"
      >
        <Search className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">{t("shell-go-to")}</span>
        <Kbd>⌘K</Kbd>
      </button>
    </div>
  );
}
