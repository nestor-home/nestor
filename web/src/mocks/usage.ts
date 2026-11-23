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

interface Person {
  id: string;
  name: string;
  written: string[]; // the channels they write on, the first most often
  weight: number; // how much they talk to Richie, relative to the others
  voice: number; // share of their written messages that are voice messages
  speaks: number; // spoken turns a day, to the satellites
}

const PEOPLE: Person[] = [
  { id: "mathis", name: "Mathis", written: ["telegram", "web", "slack"], weight: 1, voice: 0.08, speaks: 4 },
  { id: "lea", name: "Léa", written: ["telegram", "signal"], weight: 0.7, voice: 0.25, speaks: 5 },
  { id: "jules", name: "Jules", written: ["discord"], weight: 0.45, voice: 0, speaks: 3 },
  { id: "odile", name: "Odile", written: ["whatsapp", "telegram"], weight: 0.25, voice: 0.6, speaks: 2 },
];
const SESSION: Record<string, Record<string, string>> = {
  mathis: { telegram: "telegram:@mathis_l", web: "web:mathis", slack: "slack:U04MATHIS7" },
  lea: { telegram: "telegram:@lea_martin", signal: "signal:+33655504102" },
  jules: { discord: "discord:jules.lbt" },
  odile: { whatsapp: "whatsapp:33655504977", telegram: "telegram:@odile.m" },
};
const ROOMS = ["salon", "cuisine", "chambre-odile", "bureau"];

/** What OpenRouter bills Sonnet and Haiku, per million tokens: input, cached input, output. */
const RATES = {
  sonnet: [3, 0.3, 15],
  haiku: [1, 0.1, 5],
} as const;

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
    consumer: "sonnet" | "haiku" | "scribe" | "victor" | "voices",
    purpose: Purpose,
    units: Units,
    who: Partial<MockCall> = {},
  ): MockCall => {
    id += 1;
    const language = consumer === "sonnet" || consumer === "haiku";
    let cost: number | null = null;
    if (language) {
      const [input, cached, output] = RATES[consumer];
      const fresh = (units.input_tokens ?? 0) - (units.cached_input_tokens ?? 0);
      const dollars =
        (fresh * input + (units.cached_input_tokens ?? 0) * cached + (units.output_tokens ?? 0) * output) / 1e6;
      cost = Math.round(dollars * NANO);
    } else if (consumer === "scribe" && units.audio_seconds) {
      cost = Math.round(units.audio_seconds * 0.0000611 * NANO);
    } else if (consumer === "victor") {
      cost = Math.round((units.characters ?? 0) * 0.00004 * NANO);
    } else if (consumer === "voices") {
      cost = 0;
    }
    const kind = {
      sonnet: "language",
      haiku: "language",
      scribe: "transcription",
      victor: "speech",
      voices: "speaker",
    }[consumer] as MockCall["kind"];
    return {
      id: `u-${id.toString(36)}`,
      position: id,
      at: at.toISOString(),
      consumer,
      kind,
      provider: language ? "openrouter" : consumer === "voices" ? "sherpa-onnx" : "elevenlabs",
      served: {
        sonnet: "anthropic/claude-sonnet-4.6",
        haiku: "anthropic/claude-haiku-4.5",
        scribe: "scribe_v1",
        victor: "eleven_v4_turbo",
        voices: "titanet-small",
      }[consumer],
      units,
      cost_nusd: cost,
      basis: language ? "reported" : consumer === "voices" ? "free" : cost === null ? "unknown" : "priced",
      price: language ? "reported" : consumer === "voices" ? "local" : cost === null ? null : LIST,
      duration_ms: language ? whole(600, consumer === "sonnet" ? 9000 : 2400) : whole(150, 1400),
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
          session: SESSION[person.id]?.[channel] ?? `${channel}:${person.id}`,
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
          calls.push(call(moment, "sonnet", "turn", {}, { ...who, outcome: "failed", duration_ms: 30_000 }));
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
        calls.push(call(moment, "voices", "turn", { requests: 1 }, who));
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
        session: SESSION[owner.id]?.telegram ?? null,
        origin: `schedule:${schedule}`,
      });
    }
    // a task's result, now and then
    if (rand() < 0.35) {
      const moment = at(9, 21);
      if (moment)
        answer(moment, "sonnet", 2, {
          purpose: "notification",
          person: { id: "mathis", name: "Mathis" },
          channel: "telegram",
          medium: "written",
          session: SESSION.mathis?.telegram ?? null,
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
              person: { id: "mathis", name: "Mathis" },
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

// -- the ledger, as the server reads it ----------------------------------------------------------

type Dimension = S["Dimension"];
type Totals = S["TotalsOut"];
type Group = S["GroupOut"];
const DIMENSIONS: Dimension[] = [
  "consumer",
  "kind",
  "provider",
  "served",
  "purpose",
  "person",
  "channel",
  "medium",
  "basis",
  "outcome",
  "origin",
  "conversation",
];

/** A call's value of a dimension: a person by their id, `null` for a call without one. */
export function keyOf(call: MockCall, dimension: Dimension): string | null {
  if (dimension === "person") return call.person?.id ?? null;
  return (call[dimension] as string | null) ?? null;
}

/** The period and the values each dimension keeps, as the request asks (an empty value keeps the calls without
 * one); a member keeps only their own calls. */
export function filtered(calls: readonly MockCall[], query: URLSearchParams, own: string | null | undefined) {
  const until = query.get("until") ? new Date(query.get("until") as string) : new Date();
  const since = query.get("since")
    ? new Date(query.get("since") as string)
    : new Date(until.getTime() - 30 * 86_400_000);
  const only = DIMENSIONS.flatMap((d) => (query.has(d) ? [[d, new Set(query.getAll(d).map((v) => v || null))]] : []));
  const kept = calls.filter((c) => {
    const at = new Date(c.at);
    if (at < since || at >= until) return false;
    if (own !== undefined && c.person?.id !== own) return false;
    return only.every(([d, values]) => (values as Set<string | null>).has(keyOf(c, d as Dimension)));
  });
  return { kept, since, until };
}

export function totals(calls: readonly MockCall[]): Totals {
  const units: Record<string, number> = {};
  let cost = 0;
  let unknown = 0;
  let duration = 0;
  for (const c of calls) {
    if (c.cost_nusd === null || c.cost_nusd === undefined) unknown += 1;
    else cost += c.cost_nusd;
    duration += c.duration_ms;
    for (const [unit, quantity] of Object.entries(c.units)) units[unit] = (units[unit] ?? 0) + (quantity ?? 0);
  }
  return { cost_nusd: cost, calls: calls.length, unknown, units, duration_ms: duration };
}

export function groups(calls: readonly MockCall[], by: Dimension): Group[] {
  const grouped = new Map<string | null, MockCall[]>();
  for (const c of calls) {
    const key = keyOf(c, by);
    grouped.set(key, [...(grouped.get(key) ?? []), c]);
  }
  return [...grouped.entries()]
    .map(([key, kept]) => ({
      key,
      person: by === "person" && kept[0]?.person ? kept[0].person : null,
      totals: totals(kept),
    }))
    .sort((a, b) => b.totals.cost_nusd - a.totals.cost_nusd);
}

/** The start of the bucket a moment falls in, in the household's zone (UTC for Richie). */
export function bucket(at: Date, every: S["Interval"]): string {
  const day = new Date(Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate()));
  if (every === "hour") return new Date(day.getTime() + at.getUTCHours() * 3_600_000).toISOString();
  if (every === "week") return new Date(day.getTime() - ((day.getUTCDay() + 6) % 7) * 86_400_000).toISOString();
  if (every === "month") return new Date(Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), 1)).toISOString();
  return day.toISOString();
}

export function series(calls: readonly MockCall[], every: S["Interval"], by: Dimension | null): S["PointOut"][] {
  const points = new Map<string, MockCall[]>();
  for (const c of calls) {
    const start = bucket(new Date(c.at), every);
    points.set(start, [...(points.get(start) ?? []), c]);
  }
  return [...points.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([start, kept]) => ({
      start,
      groups: by ? groups(kept, by) : [{ key: null, person: null, totals: totals(kept) }],
    }));
}

export function summary(
  all: readonly MockCall[],
  query: URLSearchParams,
  own: string | null | undefined,
  now: Date = new Date(),
): S["SummaryOut"] {
  const { kept, since, until } = filtered(all, query, own);
  const span = until.getTime() - since.getTime();
  const around = (from: Date, to: Date) => {
    const asked = new URLSearchParams(query);
    asked.set("since", from.toISOString());
    asked.set("until", to.toISOString());
    return filtered(all, asked, own).kept;
  };
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const days = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate();
  const month = totals(around(monthStart, now));
  const elapsed = (now.getTime() - monthStart.getTime()) / (days * 86_400_000);
  return {
    since: since.toISOString(),
    until: until.toISOString(),
    totals: totals(kept),
    previous: totals(around(new Date(since.getTime() - span), since)),
    month,
    projected_month_nusd: elapsed > 0 ? Math.round(month.cost_nusd / elapsed) : month.cost_nusd,
    conversations: new Set(kept.map((c) => c.conversation).filter(Boolean)).size,
  };
}

/** How each model is valued when its provider says nothing: OpenRouter bills Sonnet and Haiku itself. */
export const PRICES: S["PricesOut"] = {
  catalogue: true,
  prices: [
    {
      consumer: "sonnet",
      kind: "language",
      provider: "openrouter",
      model: "anthropic/claude-sonnet-4.6",
      local: false,
      source: null,
      prices: {},
    },
    {
      consumer: "haiku",
      kind: "language",
      provider: "openrouter",
      model: "anthropic/claude-haiku-4.5",
      local: false,
      source: null,
      prices: {},
    },
    {
      consumer: "voices",
      kind: "speaker",
      provider: "sherpa-onnx",
      model: "titanet-small",
      local: true,
      source: null,
      prices: {},
    },
    {
      consumer: "scribe",
      kind: "transcription",
      provider: "elevenlabs",
      model: "scribe_v2_realtime",
      local: false,
      source: LIST,
      prices: { audio_seconds: 0.003666 },
    },
    {
      consumer: "victor",
      kind: "speech",
      provider: "elevenlabs",
      model: "eleven_v4_turbo",
      local: false,
      source: LIST,
      prices: { characters: 40 },
    },
  ],
};
