/** The spending screen's state in the URL: the period, what the chart is split by, and the values kept. */
import type { UsageDimension, UsageFilters, UsageInterval } from "@/api";
import { dimensionValues } from "@/api/schema.gen";

export const RANGES = ["today", "7d", "30d", "month", "90d"] as const;
export type Range = (typeof RANGES)[number];

/** What the chart over time can be split by. */
export const SPLITS = ["consumer", "person", "purpose", "channel", "provider"] as const satisfies UsageDimension[];
export type Split = (typeof SPLITS)[number];

export interface UsageSearch {
  range?: Range;
  by?: Split;
  /** the values each dimension keeps; "" keeps the calls without one (Nestor's own work, for a person) */
  only?: Partial<Record<UsageDimension, string[]>>;
}

export function parseUsageSearch(search: Record<string, unknown>): UsageSearch {
  const out: UsageSearch = {};
  if (RANGES.includes(search.range as Range)) out.range = search.range as Range;
  if (SPLITS.includes(search.by as Split)) out.by = search.by as Split;
  if (search.only && typeof search.only === "object") {
    const only: UsageSearch["only"] = {};
    for (const [dimension, values] of Object.entries(search.only)) {
      if (dimensionValues.includes(dimension as UsageDimension) && Array.isArray(values) && values.length)
        only[dimension as UsageDimension] = values.map(String);
    }
    if (Object.keys(only).length) out.only = only;
  }
  return out;
}

export interface Period {
  since: Date;
  until: Date;
  every: UsageInterval;
}

/** The period a range covers, up to `now` to the minute (so that every render of a minute asks the same thing), and
 * the buckets its chart is cut into. */
export function periodOf(range: Range, at: Date = new Date()): Period {
  const now = new Date(Math.floor(at.getTime() / 60_000) * 60_000);
  const midnight = new Date(now);
  midnight.setHours(0, 0, 0, 0);
  const daysBack = (days: number) => new Date(midnight.getTime() - (days - 1) * 86_400_000);
  switch (range) {
    case "today":
      return { since: midnight, until: now, every: "hour" };
    case "7d":
      return { since: daysBack(7), until: now, every: "day" };
    case "month":
      return { since: new Date(now.getFullYear(), now.getMonth(), 1), until: now, every: "day" };
    case "90d":
      return { since: daysBack(90), until: now, every: "week" };
    default:
      return { since: daysBack(30), until: now, every: "day" };
  }
}

/** What the API is asked: the period, then every value kept. */
export function filtersOf(period: Period, only: UsageSearch["only"] = {}, without?: UsageDimension): UsageFilters {
  const filters: Record<string, unknown> = { since: period.since.toISOString(), until: period.until.toISOString() };
  for (const [dimension, values] of Object.entries(only)) {
    if (dimension !== without && values?.length) filters[dimension] = values;
  }
  return filters as UsageFilters;
}

/** `only` with `value` of `dimension` added, or removed when it was there. */
export function toggled(only: UsageSearch["only"] = {}, dimension: UsageDimension, value: string | null) {
  const key = value ?? "";
  const current = only[dimension] ?? [];
  const next = current.includes(key) ? current.filter((v) => v !== key) : [...current, key];
  const { [dimension]: _dropped, ...rest } = only;
  return next.length ? { ...rest, [dimension]: next } : rest;
}
