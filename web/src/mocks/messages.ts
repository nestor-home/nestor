/**
 * The mock server's messages: day.ts writes events as their English text; this turns that text
 * into the `message {id, args}` Nestor will send, and renders it in the account's locale with
 * Nestor's own catalogues (`src/nestor/locales/<lang>/*.ftl`, read from the repository), as the
 * real server does with fluent.runtime.
 */
import { FluentBundle, FluentResource } from "@fluent/bundle";
import type { JournalEvent, JournalItem, Message } from "@/api";
import { inFrench } from "./french";

export type Lang = "en" | "fr";

const SERVER: Record<string, string> = import.meta.glob("../../../src/nestor/locales/*/*.ftl", {
  query: "?raw",
  import: "default",
  eager: true,
});

const bundles: Record<Lang, FluentBundle> = { en: bundle("en"), fr: bundle("fr") };

function bundle(locale: Lang): FluentBundle {
  const b = new FluentBundle(locale, { useIsolating: false });
  for (const [path, source] of Object.entries(SERVER)) {
    if (path.includes(`/locales/${locale}/`)) b.addResource(new FluentResource(source));
  }
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

/** "task 3f2a completed", "watch 9d41": what an unprompted message is about, as the server says it. */
const subject = (s: string, followUp: boolean): Message["args"] => {
  const follow_up = followUp ? "yes" : "no";
  const task = s.match(/^task (\S+)( completed)?/);
  if (task) return { subject: "task", id: task[1] ?? "", status: task[2] ? "completed" : "", follow_up, about: s };
  const watch = s.match(/^watch (\S+)/);
  if (watch) return { subject: "watch", id: watch[1] ?? "", status: "", follow_up, about: s };
  return { subject: "other", id: "", status: "", follow_up, about: s };
};

/** "0.8 s", "400 ms", "1 h 41", "9 min" in seconds. */
function seconds(text: string): number {
  const n = (re: RegExp) => Number(text.match(re)?.[1] ?? "0");
  if (/ms$/.test(text)) return n(/([\d.]+)\s*ms/) / 1000;
  return n(/(\d+)\s*h/) * 3600 + n(/(\d+)\s*min/) * 60 + n(/h\s*(\d+)$/) * 60 + n(/([\d.]+)\s*s$/);
}

/** The server's event type for each of its messages (the `events.py` of each Nestor module). */
export const TYPE_OF: Record<string, string> = {
  "journal-user-said": "conversation.turn.user",
  "journal-assistant-answered": "conversation.turn.assistant",
  "journal-assistant-interrupted": "conversation.turn.assistant",
  "journal-answer-cut": "conversation.turn.cut",
  "journal-fallback": "conversation.fallback",
  "journal-tool-called": "agent.tool.called",
  "journal-tool-completed": "agent.tool.completed",
  "journal-tool-failed": "agent.tool.completed",
  "journal-task-started": "task.started",
  "journal-task-progressed": "task.progress",
  "journal-task-ended": "task.ended",
  "journal-watch-created": "watch.created",
  "journal-watch-triggered": "watch.triggered",
  "journal-delivery-considered": "initiative.considered",
  "journal-delivered": "initiative.delivered",
  "journal-delivery-failed": "initiative.undeliverable",
  "journal-memory-recorded": "memory.recorded",
  "journal-connection-created": "connection.created",
  "journal-connection-changed": "connection.changed",
  "journal-presence-changed": "presence.changed",
  "journal-satellite-pairing-requested": "satellite.pairing.requested",
  "journal-person-detected": "observation.person.detected",
  "journal-speech-activity": "observation.speech.activity",
};

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
    /^Watch (\S+) triggered by “(.+)”$/,
    (m) => msg("journal-watch-triggered", { watch: m[1] ?? "", item: m[2] ?? "", urgent: "no" }),
  ],
  [
    /^Decided to speak to (\S+): (.+?)( \(follow-up\))?$/,
    (m) =>
      msg("journal-delivery-considered", { known: "yes", person: m[1] ?? "", ...subject(m[2] ?? "", Boolean(m[3])) }),
  ],
  [/^Message passed on: (.+?)( \(follow-up\))?$/, (m) => msg("journal-delivered", subject(m[1] ?? "", Boolean(m[2])))],
  [/^Message not passed on: (.+)$/, (m) => msg("journal-delivery-failed", subject(m[1] ?? "", false))],
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

/** The server's shape for an event first written as its English title and reason. */
export type Draft = Omit<JournalItem, "id" | "at" | "uid" | "kind_label" | "message" | "text" | "reason"> & {
  title: string;
  reason?: string;
};

export function toItem<T extends Draft>(
  draft: T,
): Omit<T, "title" | "reason"> & Pick<JournalItem, "message" | "text" | "reason"> {
  const { title, reason, ...rest } = draft;
  const message = parse(TITLES, title);
  return {
    ...rest,
    type: TYPE_OF[message.id] ?? rest.type,
    message,
    text: title,
    reason: reason ? { message: parse(REASONS, reason), text: reason } : null,
  };
}

/** A message in `lang`, the mock's own words in it (a room, what a watch is about) translated too. */
const said = (lang: Lang, message: Message) => render(lang, lang === "fr" ? inFrench(message) : message);

/** The event as the server sends it to an account reading `lang`. */
export function localize<E extends JournalItem | JournalEvent>(event: E, lang: Lang): E {
  return {
    ...event,
    text: event.message.id === "journal-other" ? event.text : said(lang, event.message),
    reason: event.reason ? { ...event.reason, text: said(lang, event.reason.message) } : null,
  };
}

export function errorText(lang: Lang, id: string, args: Message["args"] = {}): string {
  return render(lang, { id, args });
}
