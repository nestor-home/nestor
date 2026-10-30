/** The mock journal's queries: the same filters and counts the API computes. */
import type { Facet, JournalEvent, JournalFacets, JournalFilters, JournalItem, Person, Tone } from "@/api";

const text = (url: URL, key: string) => url.searchParams.get(key) || undefined;

export function filtersOf(url: URL): JournalFilters {
  return {
    kinds: text(url, "kinds")?.split(","),
    person: text(url, "person"),
    channel: text(url, "channel"),
    room: text(url, "room"),
    q: text(url, "q"),
    from: text(url, "from"),
    to: text(url, "to"),
    tone: text(url, "tone") as Tone | undefined,
    session: text(url, "session"),
    task: text(url, "task"),
    watch: text(url, "watch"),
    connection: text(url, "connection"),
    satellite: text(url, "satellite"),
  };
}

type Facetable = "kinds" | "person" | "channel" | "room";

function accepts(e: JournalItem, f: JournalFilters, ignore?: Facetable): boolean {
  const q = f.q?.toLowerCase();
  return (
    (ignore === "kinds" || !f.kinds?.length || f.kinds.includes(e.kind)) &&
    (ignore === "person" || !f.person || e.people.includes(f.person)) &&
    (ignore === "channel" || !f.channel || e.channels.includes(f.channel)) &&
    (ignore === "room" || !f.room || e.room === f.room) &&
    (!q || `${e.text} ${e.detail} ${e.reason?.text ?? ""}`.toLowerCase().includes(q)) &&
    (!f.from || e.at >= f.from) &&
    (!f.to || e.at <= f.to) &&
    (!f.tone || e.tone === f.tone) &&
    (!f.session || e.links.session === f.session) &&
    (!f.task || e.links.task === f.task) &&
    (!f.watch || e.links.watch === f.watch) &&
    (!f.connection || e.links.connection === f.connection) &&
    (!f.satellite || e.links.satellite === f.satellite)
  );
}

export function matching(events: JournalEvent[], f: JournalFilters): JournalEvent[] {
  return events.filter((e) => accepts(e, f));
}

export function withoutRecord({ record: _record, ...item }: JournalEvent): JournalItem {
  return item;
}

function tally(values: string[], label: (key: string) => string): Facet[] {
  const counts = new Map<string, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts]
    .map(([key, count]) => ({ key, label: label(key), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

const BUCKETS = 48;

export function facets(
  events: JournalEvent[],
  f: JournalFilters,
  people: Person[],
  kinds: Record<string, string>,
): JournalFacets {
  const names = new Map(people.map((p) => [p.id, p.name]));
  const of = (ignore: Facetable) => events.filter((e) => accepts(e, f, ignore));
  const all = matching(events, f);
  const to = f.to ? new Date(f.to) : new Date();
  const from = f.from ? new Date(f.from) : new Date(to.getTime() - 24 * 3600_000);
  const bucket = Math.max(60, Math.ceil((to.getTime() - from.getTime()) / 1000 / BUCKETS));
  const counts = new Array<number>(BUCKETS).fill(0);
  for (const e of all) {
    const i = Math.floor((new Date(e.at).getTime() - from.getTime()) / 1000 / bucket);
    if (i >= 0 && i < BUCKETS) counts[i] = (counts[i] ?? 0) + 1;
  }
  return {
    total: all.length,
    truncated: false,
    kinds: tally(
      of("kinds").map((e) => e.kind),
      (k) => kinds[k] ?? k,
    ),
    people: tally(
      of("person").flatMap((e) => e.people),
      (p) => names.get(p) ?? p,
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
