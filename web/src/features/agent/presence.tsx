/**
 * The agent's state for the whole admin (sidebar avatar, home, restart screen): read from the live
 * journal, what runs, what needs a person, and the quiet hours when the account may read them.
 */
import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { configQuery, type JournalItem, journalLatestQuery, tasksQuery } from "@/api";
import { type AgentState, agentState, isQuiet, quietHours } from "@/features/home/mind";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { startOfToday } from "@/lib/dates";
import { useCan } from "@/lib/session";

interface Presence {
  state: AgentState;
  /** The latest event, live or from today's journal: what the agent attends to. */
  latest: JournalItem | null;
  quiet: { from: number; to: number } | null;
}

const PresenceContext = createContext<Presence>({ state: "idle", latest: null, quiet: null });

export function useAgentPresence(): Presence {
  return useContext(PresenceContext);
}

export function AgentPresenceProvider({ children }: { children: ReactNode }) {
  const canTasks = useCan("tasks:read");
  const canConfig = useCan("config:manage");
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const config = useQuery({ ...configQuery, enabled: canConfig });
  const day = useQuery(journalLatestQuery({ from: startOfToday() }, 200));
  const { items: attention } = useAttention();
  const [live, setLive] = useState<JournalItem | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useLiveItems((item) => {
    setLive(item);
    setNow(Date.now());
  });
  // states fade (speaking → idle): look again shortly after the last event, then stop
  useEffect(() => {
    if (!live) return;
    const timer = setTimeout(() => setNow(Date.now()), 21_000);
    return () => clearTimeout(timer);
  }, [live]);
  const first = day.data?.items[0] ?? null;
  const latest = live && (!first || live.at >= first.at) ? live : first;
  const initiative = (config.data?.document.initiative ?? null) as Record<string, unknown> | null;
  const quiet = quietHours(initiative?.quiet_hours);
  const date = new Date(now);
  const state = agentState(
    latest ? [latest] : [],
    {
      running: tasks.data?.running.length ?? 0,
      troubled: attention.some((a) => a.tone === "error"),
      quiet: quiet ? isQuiet(quiet, date.getHours() * 60 + date.getMinutes()) : false,
    },
    now,
  );
  return <PresenceContext.Provider value={{ state, latest, quiet }}>{children}</PresenceContext.Provider>;
}
