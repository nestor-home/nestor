/**
 * The mock server's messages: day.ts writes events as their French text; this turns that text
 * into the `message {id, args}` Nestor will send, and renders it in the account's locale with the
 * server-side catalogue (`server-locales/*.ftl`), as the real server does with fluent.runtime.
 */
import { FluentBundle, FluentResource } from "@fluent/bundle";
import type { JournalEvent, JournalItem, Message } from "@/api";
import en from "./server-locales/en.ftl?raw";
import fr from "./server-locales/fr.ftl?raw";

export type Lang = "en" | "fr";

const bundles: Record<Lang, FluentBundle> = { en: bundle("en", en), fr: bundle("fr", fr) };

function bundle(locale: Lang, source: string): FluentBundle {
  const b = new FluentBundle(locale, { useIsolating: false });
  b.addResource(new FluentResource(source));
  return b;
}

export function render(lang: Lang, message: Message): string {
  const b = bundles[lang];
  const m = b.getMessage(message.id);
  return m?.value ? b.formatPattern(m.value, message.args) : message.id;
}

const msg = (id: string, args: Message["args"] = {}): Message => ({ id, args });

/** "tâche 3f2a terminée", "veille 9d41": what an unprompted message is about, as the server says it. */
const subject = (s: string, followUp: boolean): Message["args"] => {
  const task = s.match(/^tâche (\S+)( terminée)?/);
  const about = task ? `task ${task[1]}${task[2] ? " completed" : ""}` : s;
  if (task)
    return {
      subject: "task",
      id: task[1] ?? "",
      status: task[2] ? "completed" : "",
      follow_up: followUp ? "yes" : "no",
      about,
    };
  const watch = s.match(/^veille (\S+)/);
  if (watch)
    return {
      subject: "watch",
      id: watch[1] ?? "",
      status: "",
      follow_up: followUp ? "yes" : "no",
      about: `watch ${watch[1]}`,
    };
  return { subject: "other", id: "", status: "", follow_up: followUp ? "yes" : "no", about: s };
};

/** "0,8 s", "400 ms", "1 h 41", "9 min" in seconds. */
function seconds(text: string): number {
  const n = (re: RegExp) => Number((text.match(re)?.[1] ?? "0").replace(",", "."));
  if (/ms$/.test(text)) return n(/([\d,]+)\s*ms/) / 1000;
  return n(/(\d+)\s*h/) * 3600 + n(/(\d+)\s*min/) * 60 + n(/h\s*(\d+)$/) * 60 + n(/([\d,]+)\s*s$/);
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

/** Mock events are written as their French line; this reads them back as the server's messages. */
const TITLES: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [
    /^(\d+) personnes? vues? par (\S+) \(pièce « (.+) »\)$/,
    (m) => msg("journal-person-detected", { count: Number(m[1]), device: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [
    /^Parole détectée près de (\S+) \(pièce « (.+) »\)$/,
    (m) => msg("journal-speech-activity", { active: "yes", device: m[1] ?? "", room: m[2] ?? "" }),
  ],
  [
    /^(.+) est dans la pièce « (.+) »$/,
    (m) => msg("journal-presence-changed", { person: m[1] ?? "", where: "room", room: m[2] ?? "" }),
  ],
  [
    /^(.+) n'est plus à la maison$/,
    (m) => msg("journal-presence-changed", { person: m[1] ?? "", where: "away", room: "" }),
  ],
  [/^(\S+) a dit$/, (m) => msg("journal-user-said", { known: "yes", person: m[1] ?? "" })],
  [/^(\S+) a répondu \(interrompu\)$/, (m) => msg("journal-assistant-interrupted", { assistant: m[1] ?? "" })],
  [/^(\S+) a répondu$/, (m) => msg("journal-assistant-answered", { assistant: m[1] ?? "" })],
  [/^Réponse coupée par /, () => msg("journal-answer-cut")],
  [/^Réponse de secours : modèle trop lent$/, () => msg("journal-fallback", { reason: "model_slow" })],
  [/^Outil (\S+) appelé$/, (m) => msg("journal-tool-called", { tool: m[1] ?? "" })],
  [
    /^Outil (\S+) terminé en (.+)$/,
    (m) => msg("journal-tool-completed", { tool: m[1] ?? "", seconds: seconds(m[2] ?? "") }),
  ],
  [/^Outil (\S+) en échec$/, (m) => msg("journal-tool-failed", { tool: m[1] ?? "" })],
  [/^Tâche (\S+) confiée à (\S+)$/, (m) => msg("journal-task-started", { task: m[1] ?? "", executor: m[2] ?? "" })],
  [/^Tâche (\S+) : nouvelle étape$/, (m) => msg("journal-task-progressed", { task: m[1] ?? "" })],
  [
    /^Tâche (\S+) (terminée|en échec) \((.+)\)$/,
    (m) =>
      msg("journal-task-ended", {
        task: m[1] ?? "",
        status: m[2] === "terminée" ? "completed" : "failed",
        seconds: seconds(m[3] ?? ""),
      }),
  ],
  [/^Veille créée : (.+)$/, (m) => msg("journal-watch-created", { what: m[1] ?? "" })],
  [
    /^Veille (\S+) déclenchée par « (.+) »$/,
    (m) => msg("journal-watch-triggered", { watch: m[1] ?? "", item: m[2] ?? "", urgent: "no" }),
  ],
  [
    /^Décision d(?:e parler|'écrire) à (\S+) : (.+?)( \(relance\))?$/,
    (m) =>
      msg("journal-delivery-considered", { known: "yes", person: m[1] ?? "", ...subject(m[2] ?? "", Boolean(m[3])) }),
  ],
  [/^Message transmis : (.+?)( \(relance\))?$/, (m) => msg("journal-delivered", subject(m[1] ?? "", Boolean(m[2])))],
  [/^Message non transmis : (.+)$/, (m) => msg("journal-delivery-failed", subject(m[1] ?? "", false))],
  [
    /^Connexion (\S+) à réautoriser$/,
    (m) => msg("journal-connection-changed", { connection: m[1] ?? "", status: "needs_reauth" }),
  ],
  [
    /^Compte (\S+) connecté \((.+)\)$/,
    (m) => msg("journal-connection-created", { account: m[1] ?? "", kind: m[2] ?? "" }),
  ],
  [
    /^Le satellite (\S+) \((.+), pièce « (.+) »\) demande l'appairage$/,
    (m) => msg("journal-satellite-pairing-requested", { device: m[1] ?? "", model: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [/^Souvenir enregistré$/, () => msg("journal-memory-recorded")],
];

/** Why a message went where it went, as the delivery policy says it (`delivery.ftl`). */
const REASONS: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [/^(.+) est dans la pièce « (.+) »$/, (m) => msg("delivery-in-room", { person: m[1] ?? "", room: m[2] ?? "" })],
  [/^(.+) n'est pas à la maison$/, (m) => msg("delivery-away", { person: m[1] ?? "" })],
  [/^présence inconnue/, () => msg("delivery-no-presence")],
];

function parse(table: typeof TITLES, text: string): Message {
  for (const [pattern, build] of table) {
    const m = text.match(pattern);
    if (m) return build(m);
  }
  return msg("journal-other", { type: text });
}

/** The server's shape for an event first written as its French title and reason. */
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

/** The event as the server sends it to an account reading `lang`. */
export function localize<E extends JournalItem | JournalEvent>(event: E, lang: Lang): E {
  return {
    ...event,
    text: event.message.id === "journal-other" ? event.text : render(lang, event.message),
    reason: event.reason ? { ...event.reason, text: render(lang, event.reason.message) } : null,
  };
}

export function errorText(lang: Lang, id: string, args: Message["args"] = {}): string {
  return render(lang, { id, args });
}
