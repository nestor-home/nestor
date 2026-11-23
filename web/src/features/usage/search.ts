/** The spending screen's state in the URL: the period, what the chart is split by, and the values kept. */
import type { UsageDimension, UsagePeriod, UsageQuery } from "@/api";
import { dimensionValues, periodValues } from "@/api/schema.gen";

export const PERIODS = periodValues;

/** What the chart over time can be split by. */
export const SPLITS = ["consumer", "person", "purpose", "channel", "provider"] as const satisfies UsageDimension[];
export type Split = (typeof SPLITS)[number];

/** A kept value standing for the calls without one (Nestor's own work, for a person), as the API reads it. */
export const NONE = "";

export interface UsageSearch {
  period?: UsagePeriod;
  by?: Split;
  /** the values each dimension keeps (`NONE` for calls without one) */
  only?: Partial<Record<UsageDimension, string[]>>;
}

export function parseUsageSearch(search: Record<string, unknown>): UsageSearch {
  const out: UsageSearch = {};
  if (PERIODS.includes(search.period as UsagePeriod)) out.period = search.period as UsagePeriod;
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

/** What the API is asked: the period, then every value kept but those of `without` (a ranking lists all of its own). */
export function queryOf(period: UsagePeriod, only: UsageSearch["only"] = {}, without?: UsageDimension): UsageQuery {
  const kept = Object.entries(only).filter(([dimension, values]) => dimension !== without && values?.length);
  return { period, ...Object.fromEntries(kept) };
}

/** `only` with `value` of `dimension` added, or removed when it was there. */
export function toggled(only: UsageSearch["only"] = {}, dimension: UsageDimension, value: string | null) {
  const key = value ?? NONE;
  const current = only[dimension] ?? [];
  const next = current.includes(key) ? current.filter((v) => v !== key) : [...current, key];
  const { [dimension]: _dropped, ...rest } = only;
  return next.length ? { ...rest, [dimension]: next } : rest;
}
