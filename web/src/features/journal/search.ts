import type { JournalFilters } from "@/api";
import { kindValues, toneValues } from "@/api/schema.gen";
import { oneOf } from "@/lib/enums";

/** The journal's state in the URL: the API's filters, the density and the open event, all linkable. */
export interface JournalSearch extends JournalFilters {
  density?: "compact";
  event?: number; // the position of the event open in the drawer
}

/** The filters that are plain text, as `GET /journal` takes them. */
const TEXT = [
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
] as const satisfies readonly (keyof JournalFilters)[];

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export function parseJournalSearch(search: Record<string, unknown>): JournalSearch {
  const out: JournalSearch = {};
  for (const key of TEXT) {
    const value = text(search[key]);
    if (value) out[key] = value;
  }
  const kinds = Array.isArray(search.kinds) ? search.kinds.filter((k) => oneOf(kindValues, k)) : [];
  if (kinds.length) out.kinds = kinds;
  const event = Number(search.event);
  if (Number.isInteger(event) && event > 0) out.event = event;
  if (oneOf(toneValues, search.tone)) out.tone = search.tone;
  if (search.density === "compact") out.density = "compact";
  return out;
}

export function filtersOf({ density: _d, event: _e, ...filters }: JournalSearch): JournalFilters {
  return filters;
}

/** Drops empty values so the URL stays short. */
export function clean(search: JournalSearch): JournalSearch {
  return Object.fromEntries(
    Object.entries(search).filter(([, v]) => v !== undefined && v !== "" && !(Array.isArray(v) && !v.length)),
  ) as JournalSearch;
}
