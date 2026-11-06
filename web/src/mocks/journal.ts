/** The mock journal's queries: the same filters and counts the API computes. */
import type { Facet, JournalEvent, JournalFacets, JournalFilters, JournalItem } from "@/api";
import { kindValues, toneValues } from "@/api/schema.gen";
import { matches } from "@/features/journal/merge";
import { oneOf } from "@/lib/enums";

const text = (url: URL, key: string) => url.searchParams.get(key) || undefined;

/** The filters of a request, or the names of the parameters the API would refuse (422). */
export function filtersOf(url: URL): JournalFilters | string[] {
  const asked = url.searchParams.getAll("kinds");
  const kinds = asked.filter((k) => oneOf(kindValues, k));
  const asTone = text(url, "tone");
  const tone = oneOf(toneValues, asTone) ? asTone : undefined;
  if (kinds.length < asked.length || tone !== asTone) {
    return [
      ...asked.flatMap((k, i) => (oneOf(kindValues, k) ? [] : [`kinds.${i}`])),
      ...(tone !== asTone ? ["tone"] : []),
    ];
  }
  return {
    kinds,
    person: text(url, "person"),
    channel: text(url, "channel"),
    room: text(url, "room"),
    q: text(url, "q"),
    from: text(url, "from"),
    to: text(url, "to"),
    tone,
    session: text(url, "session"),
    conversation: text(url, "conversation"),
    task: text(url, "task"),
    watch: text(url, "watch"),
    connection: text(url, "connection"),
    satellite: text(url, "satellite"),
  };
}

type Facetable = "kinds" | "person" | "channel" | "room";

/** The filters with one facet's own selection set aside: a facet counts for the other filters. */
const accepts = (e: JournalItem, f: JournalFilters, ignore?: Facetable) =>
  matches(e, ignore ? { ...f, [ignore]: undefined } : f);

export function matching(events: JournalEvent[], f: JournalFilters): JournalItem[] {
  return events.map((e) => e.item).filter((e) => accepts(e, f));
}

function counted<K extends string>(values: K[]): { key: K; count: number }[] {
  const counts = new Map<K, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts].map(([key, count]) => ({ key, count })).sort((a, b) => b.count - a.count);
}

function tally(values: string[], label: (key: string) => string): Facet[] {
  return counted(values)
    .map(({ key, count }) => ({ key, label: label(key), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

const BUCKETS = 48;

export function facets(events: JournalEvent[], f: JournalFilters): JournalFacets {
  const items = events.map((e) => e.item);
  const of = (ignore: Facetable) => items.filter((e) => accepts(e, f, ignore));
  const all = items.filter((e) => accepts(e, f));
  const to = f.to ? new Date(f.to) : new Date();
  const from = f.from ? new Date(f.from) : new Date(to.getTime() - 24 * 3600_000);
  const bucket = Math.max(60, Math.ceil((to.getTime() - from.getTime()) / 1000 / BUCKETS));
  const counts = new Array<number>(BUCKETS).fill(0);
  for (const e of all) {
    const i = Math.floor((new Date(e.at).getTime() - from.getTime()) / 1000 / bucket);
    if (i >= 0 && i < BUCKETS) counts[i] = (counts[i] ?? 0) + 1;
  }
  const byPerson = of("person");
  const names = new Map<string, string>(byPerson.flatMap((e) => e.people.map((p) => [p.id, p.name])));
  return {
    total: all.length,
    truncated: false,
    kinds: counted(of("kinds").map((e) => e.kind)),
    people: tally(
      byPerson.flatMap((e) => e.people.map((p) => p.id)),
      (v) => names.get(v) ?? v,
    ),
    channels: tally(
      of("channel").flatMap((e) => e.channels),
      (c) => c,
    ),
    rooms: tally(
      of("room").flatMap((e) => (e.room ? [e.room] : [])),
      (r) => r,
    ),
    histogram: { from: from.toISOString(), to: to.toISOString(), bucket_s: bucket, counts },
  };
}
