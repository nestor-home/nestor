import type { JournalFilters, Kind } from "@/api";
import { kindValues, toneValues } from "@/api/schema.gen";

/** The journal's state in the URL: filters, density and the open event, all linkable. */
export interface JournalSearch extends Omit<JournalFilters, "kinds"> {
  kinds?: string; // comma-separated in the URL
  density?: "compact";
  event?: number; // the position of the event open in the drawer
}

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);
const oneOf = <T extends string>(values: readonly T[], value: unknown): value is T =>
  typeof value === "string" && (values as readonly string[]).includes(value);

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
  ] as const) {
    const value = text(search[key]);
    if (value) out[key] = value;
  }
  const event = Number(search.event);
  if (Number.isInteger(event) && event > 0) out.event = event;
  if (oneOf(toneValues, search.tone)) out.tone = search.tone;
  if (search.density === "compact") out.density = "compact";
  return out;
}

/** The kinds chosen in the URL that the API knows. */
export const kindsOf = (kinds: string | undefined): Kind[] =>
  (kinds?.split(",") ?? []).filter((k): k is Kind => oneOf(kindValues, k));

export function filtersOf({ kinds, density: _d, event: _e, ...rest }: JournalSearch): JournalFilters {
  const chosen = kindsOf(kinds);
  return { ...rest, ...(chosen.length ? { kinds: chosen } : {}) };
}

/** Drops empty values so the URL stays short. */
export function clean(search: JournalSearch): JournalSearch {
  return Object.fromEntries(Object.entries(search).filter(([, v]) => v !== undefined && v !== "")) as JournalSearch;
}
