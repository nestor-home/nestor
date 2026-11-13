/**
 * The mock server's messages: day.ts writes events as their English text; this turns that text
 * into the `message {id, args}` Nestor will send, and renders it in the account's locale with
 * Nestor's own catalogues (`src/nestor/locales/<lang>/*.ftl`, read from the repository), as the
 * real server does with fluent.runtime.
 */
import { FluentBundle, FluentResource } from "@fluent/bundle";
import type { EventLinks, JournalItem, Kind, Message, PersonRef, Tone } from "@/api";
import { kindValues } from "@/api/schema.gen";
import { oneOf } from "@/lib/enums";
import { inFrench } from "./french";
import kinds from "./server/journal-kinds.json";

export type Lang = "en" | "fr";

/** Nestor's whole catalogue, as `GET /i18n/{locale}` sends it (the admin bundles only its labels). */
const CATALOGUE = import.meta.glob("../../../src/nestor/locales/*/*.ftl", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

export function catalogueOf(locale: Lang): string {
  return Object.entries(CATALOGUE)
    .filter(([path]) => path.includes(`/locales/${locale}/`))
    .map(([, text]) => text)
    .join("\n");
}

const bundles: Record<Lang, FluentBundle> = { en: bundle("en"), fr: bundle("fr") };

function bundle(locale: Lang): FluentBundle {
  const b = new FluentBundle(locale, { useIsolating: false });
  b.addResource(new FluentResource(catalogueOf(locale)));
  return b;
}

/** A message the server's catalogue does not have is a mock that no longer speaks like Nestor. */
export function render(lang: Lang, message: Message): string {
  const b = bundles[lang];
  const m = b.getMessage(message.id);
  if (!m?.value) throw new Error(`the mock says ${message.id}, which Nestor's ${lang} catalogue does not have`);
  return b.formatPattern(m.value, message.args);
}

const msg = (id: string, args: Message["args"] = {}): Message => ({ id, args });

/** "task 3f2a completed", "schedule sc-tv": what an unprompted message is about, as the server says it. */
const subject = (s: string, followUp = false): Message["args"] => {
  const [source = "", id = "", status = ""] = s.split(" ");
  return { subject: source, id, status, follow_up: followUp ? "yes" : "no" };
};

/** "0.8 s", "400 ms", "1 h 41", "9 min" in seconds. */
function seconds(text: string): number {
  const n = (re: RegExp) => Number(text.match(re)?.[1] ?? "0");
  if (/ms$/.test(text)) return n(/([\d.]+)\s*ms/) / 1000;
  return n(/(\d+)\s*h/) * 3600 + n(/(\d+)\s*min/) * 60 + n(/h\s*(\d+)$/) * 60 + n(/([\d.]+)\s*s$/);
}

/** Mock events are written as their English line; this reads them back as the server's messages. */
const TITLES: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [
    /^(\d+) (?:person|people) seen by (\S+) \(room “(.+)”\)$/,
    (m) => msg("journal-person-detected", { count: Number(m[1]), device: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [
    /^Speech detected near (\S+) \(room “(.+)”\)$/,
    (m) => msg("journal-speech-activity", { active: "yes", device: m[1] ?? "", room: m[2] ?? "" }),
  ],
  [
    /^(.+) is in the (.+)$/,
    (m) => msg("journal-presence-changed", { person: m[1] ?? "", where: "room", room: m[2] ?? "" }),
  ],
  [/^(.+) is no longer home$/, (m) => msg("journal-presence-changed", { person: m[1] ?? "", where: "away", room: "" })],
  [/^(\S+) said$/, (m) => msg("journal-user-said", { known: "yes", by: "account", person: m[1] ?? "" })],
  [/^(\S+) answered \(interrupted\)$/, (m) => msg("journal-assistant-interrupted", { assistant: m[1] ?? "" })],
  [/^(\S+) answered$/, (m) => msg("journal-assistant-answered", { assistant: m[1] ?? "" })],
  [/^Answer cut off/, () => msg("journal-answer-cut")],
  [/^Fallback answer: model too slow$/, () => msg("journal-fallback", { reason: "model_slow" })],
  [
    /^(\S+) failed: (\S+) takes over$/,
    (m) => msg("journal-model-fell-back", { model: m[1] ?? "", fallback: m[2] ?? "" }),
  ],
  [/^Tool (\S+) called$/, (m) => msg("journal-tool-called", { tool: m[1] ?? "" })],
  [
    /^Tool (\S+) finished in (.+)$/,
    (m) => msg("journal-tool-completed", { tool: m[1] ?? "", seconds: seconds(m[2] ?? "") }),
  ],
  [/^Tool (\S+) failed$/, (m) => msg("journal-tool-failed", { tool: m[1] ?? "" })],
  [/^Task (\S+) handed to (\S+)$/, (m) => msg("journal-task-started", { task: m[1] ?? "", executor: m[2] ?? "" })],
  [/^Task (\S+): new step$/, (m) => msg("journal-task-progressed", { task: m[1] ?? "" })],
  [
    /^Task (\S+) (completed|failed) \((.+)\)$/,
    (m) => msg("journal-task-ended", { task: m[1] ?? "", status: m[2] ?? "", seconds: seconds(m[3] ?? "") }),
  ],
  [/^Watch created: (.+)$/, (m) => msg("journal-watch-created", { what: m[1] ?? "" })],
  [
    /^“(.+)” checked against (\d+) watch(?:es)?: (none match|(\d+) matched)$/,
    (m) =>
      msg("journal-watch-sorted", {
        item: m[1] ?? "",
        asked: Number(m[2]),
        matched: Number(m[4] ?? "0"),
        unsorted: "no",
      }),
  ],
  [
    /^Watch (\S+) triggered by “(.+)”$/,
    (m) => msg("journal-watch-triggered", { watch: m[1] ?? "", item: m[2] ?? "", urgent: "no" }),
  ],
  [
    /^Decided to speak to (\S+): (.+)$/,
    (m) => msg("journal-delivery-considered", { known: "yes", person: m[1] ?? "", ...subject(m[2] ?? "") }),
  ],
  [/^Message passed on: (.+?)( \(follow-up\))?$/, (m) => msg("journal-delivered", subject(m[1] ?? "", Boolean(m[2])))],
  [/^Message not passed on: (.+)$/, (m) => msg("journal-delivery-failed", subject(m[1] ?? ""))],
  [/^Nothing to tell: (.+)$/, (m) => msg("journal-delivery-withheld", subject(m[1] ?? ""))],
  [
    /^Connection (\S+) needs to be authorised again$/,
    (m) => msg("journal-connection-changed", { connection: m[1] ?? "", status: "needs_reauth" }),
  ],
  [
    /^Account (\S+) connected \((.+)\)$/,
    (m) => msg("journal-connection-created", { account: m[1] ?? "", kind: m[2] ?? "" }),
  ],
  [
    /^Satellite (\S+) \((.+), room “(.+)”\) asks to pair$/,
    (m) => msg("journal-satellite-pairing-requested", { device: m[1] ?? "", model: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [/^Memory recorded$/, () => msg("journal-memory-recorded", { drawn: "no" })],
];

/** Why a message went where it went, as the delivery policy says it (`delivery.ftl`). */
const REASONS: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [/^(.+) is in the (.+)$/, (m) => msg("delivery-in-room", { person: m[1] ?? "", room: m[2] ?? "" })],
  [/^(.+) is away$/, (m) => msg("delivery-away", { person: m[1] ?? "" })],
  [/^no presence information/, () => msg("delivery-no-presence")],
];

function parse(table: typeof TITLES, text: string): Message {
  for (const [pattern, build] of table) {
    const m = text.match(pattern);
    if (m) return build(m);
  }
  return msg("journal-other", { type: text });
}

/** A mock event as day.ts writes it: its English title and reason, and only the links it has. */
export interface Draft {
  type: string;
  title: string;
  detail?: string;
  reason?: string;
  people?: PersonRef[];
  channels?: string[];
  room?: string | null;
  tone?: Tone;
  links?: Partial<EventLinks>;
  outcome?: JournalItem["outcome"];
  attachments?: JournalItem["attachments"];
  tool?: string | null;
  brand?: string | null;
}

const NO_LINKS: EventLinks = {
  session: null,
  conversation: null,
  turn: null,
  call: null,
  task: null,
  watch: null,
  delivery: null,
  connection: null,
  satellite: null,
  memory: null,
};

/** The journal kind of an event type, as the server groups them (`nestor admin mocks`); `other` when none. */
const KINDS: Record<string, string> = kinds;
const kindOf = (type: string): Kind => {
  const kind = KINDS[type];
  return oneOf(kindValues, kind) ? kind : "other";
};

/** The item the server would send for a draft, at its place in the journal (texts in English). */
export function toItem(draft: Draft, where: { position: number; id: string; at: string }): JournalItem {
  const message = parse(TITLES, draft.title);
  const detail = draft.detail ?? "";
  return {
    ...where,
    type: draft.type,
    kind: kindOf(draft.type),
    message,
    text: draft.title,
    detail,
    detail_message: null,
    detail_text: detail,
    reason: draft.reason ? { message: parse(REASONS, draft.reason), text: draft.reason } : null,
    tone: draft.tone ?? "normal",
    people: draft.people ?? [],
    channels: draft.channels ?? [],
    room: draft.room ?? null,
    tool: draft.tool ?? null,
    outcome: draft.outcome ?? null,
    attachments: draft.attachments ?? [],
    brand: draft.brand ?? draft.channels?.[0] ?? null,
    links: { ...NO_LINKS, ...draft.links },
    cause: null,
  };
}

/** A message in `lang`, the mock's own words in it (a room, what a watch is about) translated too. */
const said = (lang: Lang, message: Message) => render(lang, lang === "fr" ? inFrench(message) : message);

/** The item as the server sends it to an account reading `lang`. */
export function localize(item: JournalItem, lang: Lang): JournalItem {
  return {
    ...item,
    text: item.message.id === "journal-other" ? item.text : said(lang, item.message),
    reason: item.reason ? { ...item.reason, text: said(lang, item.reason.message) } : null,
  };
}

export function errorText(lang: Lang, id: string, args: Message["args"] = {}): string {
  return render(lang, { id, args });
}
