import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { type JournalItem, type JournalStream, type Kind, keys, type LiveStatus } from "@/api";

type Listener = (item: JournalItem) => void;

interface Live {
  status: LiveStatus;
  listen: (listener: Listener) => () => void;
}

const LiveContext = createContext<Live | null>(null);

// what a live item makes stale elsewhere in the admin, by its kind (the journal's categories)
const STALE: Partial<Record<Kind, readonly (readonly unknown[])[]>> = {
  task: [keys.tasks],
  watch: [keys.watches],
  memory: [["memories"]],
  connection: [keys.connections],
  satellite: [keys.satellites, keys.home], // its list and each satellite: a connection, an update reported
  presence: [keys.people, keys.home],
  schedule: [keys.schedules],
  delivery: [keys.messages], // a message passed on, delivered or not
  tool: [keys.confirmations], // a confirmation asked or answered
};

/** One stream for the whole admin: the shell shows its status, the journal page listens to it. */
export function LiveProvider({ stream, children }: { stream: JournalStream; children: ReactNode }) {
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const listeners = useRef(new Set<Listener>());
  const queryClient = useQueryClient();

  useEffect(
    () =>
      stream.subscribe(
        (item) => {
          for (const listener of listeners.current) listener(item);
          for (const queryKey of STALE[item.kind] ?? []) void queryClient.invalidateQueries({ queryKey });
        },
        setStatus,
        (activity) => queryClient.setQueryData(keys.activity, activity),
      ),
    [stream, queryClient],
  );

  const listen = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  const value = useMemo<Live>(() => ({ status, listen }), [status, listen]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): Live {
  const live = useContext(LiveContext);
  if (!live) throw new Error("useLive outside LiveProvider");
  return live;
}

/** Calls `listener` for each new journal item while the component is mounted. */
export function useLiveItems(listener: Listener): void {
  const { listen } = useLive();
  const latest = useRef(listener);
  latest.current = listener;
  useEffect(() => listen((item) => latest.current(item)), [listen]);
}
