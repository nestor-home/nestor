/**
 * What Richie cost the Martins, call by call, over the last four months: the ledger the server keeps, as its
 * `usage.recorded` events would have filled it. Written once from a seeded generator, so that every screen and
 * test reads the same calls; the handlers then answer from it as the server's ledger does (`usage` handlers).
 *
 * The models and their prices are those of `instance.ts`: Sonnet writes, Haiku speaks and sorts the mail (both
 * through OpenRouter, which bills each call), ElevenLabs hears voice messages and records the answers to them
 * (priced from the public list), the voice model runs on the house's own machine.
 */
import type { components } from "@/api/schema.gen";
import { document, household } from "./instance";

type S = components["schemas"];
export type MockCall = S["CallOut"];
type Units = MockCall["units"];
type Purpose = MockCall["purpose"];

export const DAYS = 120;
const LIST = "catalogue:2026-11-23";

/** Mulberry32: the same calls on every load. */
function random(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** How each person of the household uses Richie; who they are and where they write come from `instance.ts`. */
interface Habit {
  written: string[]; // the channels they write on, the first most often
  weight: number; // how much they talk to Richie, relative to the others
  voice: number; // share of their written messages that are voice messages
  speaks: number; // spoken turns a day, to the satellites
}

const HABITS: Record<string, Habit> = {
  mathis: { written: ["telegram", "web", "slack"], weight: 1, voice: 0.08, speaks: 4 },
  lea: { written: ["telegram", "signal"], weight: 0.7, voice: 0.25, speaks: 5 },
  jules: { written: ["discord"], weight: 0.45, voice: 0, speaks: 3 },
  odile: { written: ["whatsapp", "telegram"], weight: 0.25, voice: 0.6, speaks: 2 },
};
const ROOMS = ["salon", "cuisine", "chambre-odile", "bureau"];

const config = document();
const PEOPLE = household(config).map((p) => ({
  ...p,
  ...(HABITS[p.id] ?? { written: [], weight: 0, voice: 0, speaks: 0 }),
  /** the address they write from on a channel: the account it knows them by (the admin's chat by their id) */
  session: (channel: string) => p.accounts.find((a) => a.startsWith(`${channel}:`)) ?? `${channel}:${p.id}`,
}));
const named = (id: string) => {
  const person = PEOPLE.find((p) => p.id === id);
  return person ? { id: person.id, name: person.name } : null;
};

type Consumer = "sonnet" | "haiku" | "scribe" | "victor" | "voices";

/** Each model of the file as the ledger names it: its type, who bills it, the model it serves. */
const MODELS = Object.fromEntries(
  Object.entries(config.models as Record<string, Record<string, unknown>>).map(([key, m]) => [
    key,
    {
      kind: m.type as MockCall["kind"],
      provider: String(m.base_url ?? "").includes("openrouter.ai") ? "openrouter" : String(m.provider),
      served: String(m.file_model ?? m.model),
      local: m.provider === "sherpa-onnx",
    },
  ]),
) as Record<Consumer, { kind: MockCall["kind"]; provider: string; served: string; local: boolean }>;

/** What a call costs: what OpenRouter bills Sonnet and Haiku per million tokens (input, cached, output); ElevenLabs
 * from the public list, by the second heard and by the character spoken. */
const BILLED = { sonnet: [3, 0.3, 15], haiku: [1, 0.1, 5] } as const;
const LISTED = { scribe: { audio_seconds: 0.0000611 }, victor: { characters: 0.00004 } } as const;

const NANO = 1e9;

export function mockCalls(now: Date = new Date()): MockCall[] {
  const rand = random(20261123);
  const between = (low: number, high: number) => low + (high - low) * rand();
  const whole = (low: number, high: number) => Math.round(between(low, high));
  const pick = <T>(items: readonly T[]): T => items[Math.floor(rand() * items.length)] as T;
  const calls: MockCall[] = [];
  let id = 0;

  const call = (
    at: Date,
    consumer: Consumer,
    purpose: Purpose,
    units: Units,
    who: Partial<MockCall> = {},
  ): MockCall => {
    id += 1;
    const model = MODELS[consumer];
    let cost: number | null = null;
    let price: string | null = null;
    if (consumer === "sonnet" || consumer === "haiku") {
      const [input, cached, output] = BILLED[consumer];
      const fresh = (units.input_tokens ?? 0) - (units.cached_input_tokens ?? 0);
      const dollars =
        (fresh * input + (units.cached_input_tokens ?? 0) * cached + (units.output_tokens ?? 0) * output) / 1e6;
      cost = Math.round(dollars * NANO);
    } else if (consumer === "voices") {
      cost = 0; // on the house's own machine
    } else {
      const [unit, perUnit] = Object.entries(LISTED[consumer])[0] as [keyof Units, number];
      const quantity = units[unit];
      if (quantity) [cost, price] = [Math.round(quantity * perUnit * NANO), LIST];
    }
    const billed = consumer === "sonnet" || consumer === "haiku";
    return {
      id: `u-${id.toString(36)}`,
      position: id,
      at: at.toISOString(),
      consumer,
      kind: model.kind,
      provider: model.provider,
      served: model.served,
      units: { ...units, requests: 1 }, // a call is a request, as every adapter reports
      cost_nusd: cost,
      basis: billed ? "reported" : model.local ? "free" : cost === null ? "unknown" : "priced",
      price,
      duration_ms: billed ? whole(600, consumer === "sonnet" ? 9000 : 2400) : whole(150, 1400),
      outcome: "ok",
      purpose,
      person: null,
      channel: null,
      medium: null,
      session: null,
      conversation: null,
      turn: null,
      origin: null,
      ...who,
    };
  };

  /** An answer: one model call per round of tools, the conversation's prompt read mostly from the cache. */
  const answer = (at: Date, consumer: "sonnet" | "haiku", rounds: number, who: Partial<MockCall>, heavy = 1) => {
    let prompt = whole(5200, 9000) * heavy;
    for (let round = 0; round < rounds; round += 1) {
      const cached = round === 0 ? Math.round(prompt * between(0.55, 0.9)) : Math.round(prompt * 0.95);
      const output = whole(40, round === rounds - 1 ? 520 : 140) * (heavy > 1 ? 3 : 1);
      calls.push(
        call(
          new Date(at.getTime() + round * 4000),
          consumer,
          who.purpose ?? "turn",
          { input_tokens: prompt, cached_input_tokens: cached, output_tokens: output },
          who,
        ),
      );
      prompt += output + whole(300, 2400) * heavy; // what the tool brought back
    }
  };

  const today = new Date(now);
  today.setUTCHours(0, 0, 0, 0);
  for (let day = DAYS - 1; day >= 0; day -= 1) {
    const start = new Date(today.getTime() - day * 86_400_000);
    const weekend = start.getUTCDay() === 0 || start.getUTCDay() === 6;
    const growth = 0.55 + 0.45 * ((DAYS - day) / DAYS); // the household uses Richie more as weeks go by
    const at = (from: number, to: number) => {
      const moment = new Date(start.getTime() + between(from, to) * 3_600_000);
      return moment > now ? null : moment;
    };
    let conversation = 0;
    for (const person of PEOPLE) {
      const written = Math.round(between(2, 9) * person.weight * growth * (weekend ? 1.3 : 1));
      for (let n = 0; n < written; n += 1) {
        const evening = rand() < 0.55;
        const moment = at(evening ? 17.5 : 7, evening ? 23 : 17.5);
        if (!moment) continue;
        const channel = rand() < 0.7 ? (person.written[0] as string) : pick(person.written);
        conversation += 1;
        const who: Partial<MockCall> = {
          person: { id: person.id, name: person.name },
          channel,
          medium: "written",
          session: person.session(channel),
          conversation: `c-${day}-${conversation}`,
          turn: `t-${day}-${conversation}`,
        };
        if (rand() < person.voice) {
          const seconds = Math.round(between(4, 48) * 10) / 10;
          const unreadable = rand() < 0.04; // a recording the server could not measure: its cost stays unknown
          calls.push(call(moment, "scribe", "turn", unreadable ? {} : { audio_seconds: seconds }, who));
          calls.push(call(new Date(moment.getTime() + 9000), "victor", "turn", { characters: whole(90, 520) }, who));
        }
        if (rand() < 0.03) {
          calls.push(
            call(
              moment,
              "sonnet",
              "turn",
              {},
              {
                ...who,
                outcome: "failed", // before it was sent: nothing consumed, nothing billed
                duration_ms: 30_000,
                units: {},
                cost_nusd: 0,
                basis: "nothing",
                price: null,
              },
            ),
          );
          answer(moment, "haiku", whole(1, 3), who); // the fallback answers
        } else {
          answer(moment, "sonnet", whole(1, rand() < 0.25 ? 5 : 3), who);
        }
        if (channel === "web" && rand() < 0.6) {
          calls.push(
            call(
              new Date(moment.getTime() + 20_000),
              "sonnet",
              "title",
              {
                input_tokens: whole(180, 420),
                output_tokens: whole(6, 14),
              },
              who,
            ),
          );
        }
        if (rand() < 0.45) {
          answer(new Date(moment.getTime() + 3_600_000), "sonnet", 1, { ...who, purpose: "consolidation" }, 0.6);
        }
      }
      const spoken = Math.round(between(0, 2) * person.speaks * growth * (weekend ? 1.4 : 1));
      for (let n = 0; n < spoken; n += 1) {
        const moment = at(rand() < 0.6 ? 17 : 6.5, rand() < 0.6 ? 22 : 9);
        if (!moment) continue;
        const room = pick(ROOMS);
        conversation += 1;
        const who: Partial<MockCall> = {
          person: { id: person.id, name: person.name },
          channel: "satellites",
          medium: "spoken",
          session: `satellites:${room}`,
          conversation: `c-${day}-${conversation}`,
          turn: `t-${day}-${conversation}`,
        };
        calls.push(call(moment, "voices", "turn", {}, who));
        const cut = rand() < 0.08; // interrupted halfway: billed as far as it went
        answer(moment, "haiku", cut ? 1 : whole(1, 2), cut ? { ...who, outcome: "cancelled" } : who);
      }
    }
    // the mail every watch is sorted against
    const mails = Math.round(between(14, 34) * growth * (weekend ? 0.6 : 1));
    for (let n = 0; n < mails; n += 1) {
      const moment = at(6, 23.5);
      if (!moment) continue;
      const owner = rand() < 0.6 ? PEOPLE[0] : PEOPLE[1];
      calls.push(
        call(
          moment,
          "haiku",
          "watch",
          { input_tokens: whole(900, 2600), output_tokens: whole(18, 60) },
          { person: owner ? { id: owner.id, name: owner.name } : null, origin: rand() < 0.35 ? pick(WATCHES) : null },
        ),
      );
    }
    // reminders and the morning TV-price check, each told to whom it is for
    for (const [schedule, person, hour] of SCHEDULES) {
      if (schedule === "sc-bins" && start.getUTCDay() !== 2) continue;
      const moment = at(hour, hour + 0.05);
      const owner = PEOPLE.find((p) => p.id === person);
      if (!moment || !owner) continue;
      answer(moment, "sonnet", schedule === "sc-tv" ? 3 : 1, {
        purpose: "notification",
        person: { id: owner.id, name: owner.name },
        channel: "telegram",
        medium: "written",
        session: owner.session("telegram"),
        origin: `schedule:${schedule}`,
      });
    }
    // a task's result, now and then
    if (rand() < 0.35) {
      const moment = at(9, 21);
      if (moment)
        answer(moment, "sonnet", 2, {
          purpose: "notification",
          person: named("mathis"),
          channel: "telegram",
          medium: "written",
          session: PEOPLE[0]?.session("telegram") ?? null,
          origin: `task:${pick(TASKS)}`,
        });
    }
    // the day Mathis had Richie go through the whole insurance file: one long, heavy conversation
    if (day === 12) {
      const moment = at(20, 20.2);
      if (moment)
        for (let round = 0; round < 6; round += 1)
          answer(
            new Date(moment.getTime() + round * 300_000),
            "sonnet",
            4,
            {
              person: named("mathis"),
              channel: "web",
              medium: "written",
              session: "web:mathis",
              conversation: `c-${day}-insurance`,
              turn: `t-${day}-insurance-${round}`,
            },
            4,
          );
    }
  }
  calls.sort((a, b) => a.at.localeCompare(b.at));
  return calls.map((c, index) => ({ ...c, position: index + 1 }));
}

const WATCHES = ["watch:w-9d41", "watch:w-2b77", "watch:w-f31a", "watch:w-p8c2"] as const;
const TASKS = ["t-4410aa", "t-88b07e", "t-3f2a1c", "t-a04f12", "t-5e6b70"] as const;
const SCHEDULES: [string, string, number][] = [
  ["sc-tv", "mathis", 7.5],
  ["sc-bread", "mathis", 17.75],
  ["sc-plants", "lea", 8.25],
  ["sc-bins", "jules", 19.5],
];

// -- the ledger, as the server reads it, in Richie's zone (UTC) ---------------------------------------

type Dimension = S["Dimension"];
type Period = S["Period"];
type Span = S["SpanOut"];
type Totals = S["TotalsOut"];
type Group = S["GroupOut"];
const DAY = 86_400_000;

/** A call's value of a dimension: a person by their id, `null` for a call without one. */
export function keyOf(call: MockCall, dimension: Dimension): string | null {
  if (dimension === "person") return call.person?.id ?? null;
  return (call[dimension] as string | null) ?? null;
}

/** A period up to now, as the server resolves it: from today's midnight back, or from the month's first. */
export function spanOf(period: Period, now: Date = new Date()): Span {
  const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const back = { today: 1, "7d": 7, "30d": 30, "90d": 90, month: 0 }[period];
  const since = period === "month" ? Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1) : midnight - (back - 1) * DAY;
  const every = period === "today" ? "hour" : period === "90d" ? "week" : "day";
  return { since: new Date(since).toISOString(), until: now.toISOString(), every };
}

/** The calls between `span`'s ends that the request keeps of each dimension (an empty value keeps the calls without
 * one); a member keeps only their own (`own`). */
export function within(calls: readonly MockCall[], span: Span, query: URLSearchParams, own: string | null | undefined) {
  const [since, until] = [span.since, span.until];
  const kept = [...new Set(query.keys())]
    .filter((d) => d !== "period" && d !== "by" && d !== "before" && d !== "limit")
    .map((d) => [d as Dimension, new Set(query.getAll(d).map((v) => v || null))] as const);
  return calls.filter(
    (c) =>
      c.at >= since &&
      c.at < until &&
      (own === undefined || c.person?.id === own) &&
      kept.every(([d, values]) => values.has(keyOf(c, d))),
  );
}

export function totals(calls: readonly MockCall[]): Totals {
  const units: Record<string, number> = {};
  const conversations = new Set<string>();
  let [cost, unknown, duration, conversed] = [0, 0, 0, 0];
  for (const c of calls) {
    if (c.cost_nusd === null || c.cost_nusd === undefined) unknown += 1;
    else cost += c.cost_nusd;
    duration += c.duration_ms;
    if (c.conversation) {
      conversations.add(c.conversation);
      conversed += c.cost_nusd ?? 0;
    }
    for (const [unit, quantity] of Object.entries(c.units)) units[unit] = (units[unit] ?? 0) + (quantity ?? 0);
  }
  return {
    cost_nusd: cost,
    calls: calls.length,
    unknown,
    units,
    duration_ms: duration,
    conversations: conversations.size,
    conversed_nusd: conversed,
  };
}

/** The calls by a key, in one pass. */
function byKey(calls: readonly MockCall[], key: (c: MockCall) => string | null): Map<string | null, MockCall[]> {
  const grouped = new Map<string | null, MockCall[]>();
  for (const c of calls) {
    const k = key(c);
    const kept = grouped.get(k);
    if (kept) kept.push(c);
    else grouped.set(k, [c]);
  }
  return grouped;
}

export function groups(calls: readonly MockCall[], by: Dimension): Group[] {
  return [...byKey(calls, (c) => keyOf(c, by)).entries()]
    .map(([key, kept]) => ({ key, person: by === "person" ? (kept[0]?.person ?? null) : null, totals: totals(kept) }))
    .sort((a, b) => b.totals.cost_nusd - a.totals.cost_nusd);
}

/** When a bucket starts: the hour, the day, its week's Monday, its month's first. */
function bucket(at: Date, every: S["Interval"]): string {
  const day = Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate());
  if (every === "hour") return new Date(day + at.getUTCHours() * 3_600_000).toISOString();
  if (every === "week") return new Date(day - ((at.getUTCDay() + 6) % 7) * DAY).toISOString();
  if (every === "month") return new Date(Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), 1)).toISOString();
  return new Date(day).toISOString();
}

export function series(calls: readonly MockCall[], every: S["Interval"], by: Dimension | null): S["PointOut"][] {
  return [...byKey(calls, (c) => bucket(new Date(c.at), every)).entries()]
    .sort(([a], [b]) => String(a).localeCompare(String(b)))
    .map(([start, kept]) => ({
      start: String(start),
      groups: by ? groups(kept, by) : [{ key: null, person: null, totals: totals(kept) }],
    }));
}

export function rhythm(calls: readonly MockCall[]): S["BeatOut"][] {
  return [
    ...byKey(calls, (c) => {
      const at = new Date(c.at);
      return `${(at.getUTCDay() + 6) % 7}-${at.getUTCHours()}`;
    }).entries(),
  ].map(([key, kept]) => {
    const [weekday, hour] = String(key).split("-").map(Number);
    const spent = totals(kept);
    return { weekday: weekday ?? 0, hour: hour ?? 0, cost_nusd: spent.cost_nusd, calls: spent.calls };
  });
}

export function summary(
  all: readonly MockCall[],
  query: URLSearchParams,
  own: string | null | undefined,
  now: Date = new Date(),
): S["SummaryOut"] {
  const span = spanOf((query.get("period") ?? "30d") as Period, now);
  const length = new Date(span.until).getTime() - new Date(span.since).getTime();
  const before = { ...span, since: new Date(new Date(span.since).getTime() - length).toISOString(), until: span.since };
  const month = spanOf("month", now);
  const days = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate();
  const so_far = totals(within(all, month, query, own));
  const elapsed = (now.getTime() - new Date(month.since).getTime()) / (days * DAY);
  return {
    span,
    totals: totals(within(all, span, query, own)),
    previous: totals(within(all, before, query, own)),
    month: so_far,
    projected_month_nusd: elapsed > 0 ? Math.round(so_far.cost_nusd / elapsed) : so_far.cost_nusd,
  };
}

/** How each model of the file is valued when its provider says nothing: OpenRouter bills Sonnet and Haiku itself,
 * ElevenLabs is priced from the public list, written as providers write prices. */
export const PRICES: S["PricesOut"] = {
  catalogue: true,
  prices: Object.entries(MODELS).map(([consumer, m]) => {
    const listed: Record<string, number> = LISTED[consumer as keyof typeof LISTED] ?? {};
    const per = { audio_seconds: 60, characters: 1_000_000 } as Record<string, number>;
    return {
      consumer,
      kind: m.kind,
      provider: m.provider,
      model: m.served,
      local: m.local,
      source: Object.keys(listed).length ? LIST : null,
      prices: Object.fromEntries(Object.entries(listed).map(([unit, perUnit]) => [unit, perUnit * (per[unit] ?? 1)])),
    };
  }),
};
