import type { JournalFilters } from "@/api";

/** The journal's state in the URL: filters, density and the open event, all linkable. */
export interface JournalSearch extends Omit<JournalFilters, "kinds"> {
  kinds?: string; // comma-separated in the URL
  density?: "compact";
  event?: string; // the event open in the drawer
}

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export function parseJournalSearch(search: Record<string, unknown>): JournalSearch {
  const out: JournalSearch = {};
  for (const key of [
    "kinds",
    "person",
    "channel",
    "room",
    "q",
    "from",
    "to",
    "session",
    "conversation",
    "task",
    "watch",
    "connection",
    "satellite",
    "event",
  ] as const) {
    const value = text(search[key]);
    if (value) out[key] = value;
  }
  if (search.tone === "warning" || search.tone === "decision") out.tone = search.tone;
  if (search.density === "compact") out.density = "compact";
  return out;
}

export function filtersOf({ kinds, density: _d, event: _e, ...rest }: JournalSearch): JournalFilters {
  return { ...rest, ...(kinds ? { kinds: kinds.split(",") } : {}) };
}

/** Drops empty values so the URL stays short. */
export function clean(search: JournalSearch): JournalSearch {
  return Object.fromEntries(Object.entries(search).filter(([, v]) => v !== undefined && v !== "")) as JournalSearch;
}
