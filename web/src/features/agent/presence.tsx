/**
 * The agent's state for the whole admin (sidebar, home, restart): what Nestor says it is doing
 * (`GET /agent/activity`, kept current by the stream's `activity` events), shown as concerned when
 * it is otherwise idle and something is broken. The latest journal event says what it attends to;
 * the quiet hours come from `GET /agent/initiative`.
 */
import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useState } from "react";
import { type AgentActivity, activityQuery, initiativeQuery, type JournalItem, journalLatestQuery } from "@/api";
import type { AgentState } from "@/features/home/mind";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { startOfToday } from "@/lib/dates";
import { useCan } from "@/lib/session";

export interface Quiet {
  from: number; // minutes since midnight, household time
  to: number;
  active: boolean;
}

interface Presence {
  state: AgentState;
  activity: AgentActivity | null;
  /** The latest event, live or from today's journal: what the agent attends to. */
  latest: JournalItem | null;
  quiet: Quiet | null;
}

const PresenceContext = createContext<Presence>({ state: "idle", activity: null, latest: null, quiet: null });

export function useAgentPresence(): Presence {
  return useContext(PresenceContext);
}

const minutes = (hhmm: string) => {
  const [h = 0, m = 0] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

/** The agent's state from its activity: concerned when it has nothing to do but something is broken. */
export function stateOf(activity: AgentActivity | null, troubled: boolean): AgentState {
  const state = activity?.state ?? "idle";
  return state === "idle" && troubled ? "concerned" : state;
}

export function AgentPresenceProvider({ children }: { children: ReactNode }) {
  const canAgent = useCan("agent:read");
  const activity = useQuery({ ...activityQuery, enabled: canAgent });
  const initiative = useQuery({ ...initiativeQuery, enabled: canAgent });
  const day = useQuery(journalLatestQuery({ from: startOfToday() }, 200));
  const { items: attention } = useAttention();
  const [live, setLive] = useState<JournalItem | null>(null);
  useLiveItems(setLive);
  const first = day.data?.items[0] ?? null;
  const latest = live && (!first || live.at >= first.at) ? live : first;
  const hours = initiative.data?.quiet_hours ?? null;
  const quiet = hours ? { from: minutes(hours.start), to: minutes(hours.end), active: hours.active } : null;
  const state = stateOf(
    activity.data ?? null,
    attention.some((a) => a.tone === "error"),
  );
  return (
    <PresenceContext.Provider value={{ state, activity: activity.data ?? null, latest, quiet }}>
      {children}
    </PresenceContext.Provider>
  );
}
