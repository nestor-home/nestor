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

const subject = (s: string): Message["args"] => {
  const task = s.match(/^tâche (\S+)( terminée)?/);
  if (task) return { subject: "task", ref: task[1] ?? "", done: task[2] ? "yes" : "no" };
  const watch = s.match(/^veille (\S+)/);
  if (watch) return { subject: "watch", ref: watch[1] ?? "" };
  return { subject: "other", ref: s };
};

const TITLES: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [
    /^(\d+) personnes? vues? par (\S+) \(pièce « (.+) »\)$/,
    (m) => msg("journal-person-detected", { count: Number(m[1]), device: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [
    /^Parole détectée près de (\S+) \(pièce « (.+) »\)$/,
    (m) => msg("journal-speech-detected", { device: m[1] ?? "", room: m[2] ?? "" }),
  ],
  [/^(.+) est dans la pièce « (.+) »$/, (m) => msg("journal-presence-room", { name: m[1] ?? "", room: m[2] ?? "" })],
  [/^(.+) n'est plus à la maison$/, (m) => msg("journal-presence-away", { name: m[1] ?? "" })],
  [/^(\S+) a dit$/, (m) => msg("journal-user-said", { name: m[1] ?? "" })],
  [/^(\S+) a répondu \(interrompu\)$/, (m) => msg("journal-assistant-interrupted", { assistant: m[1] ?? "" })],
  [/^(\S+) a répondu$/, (m) => msg("journal-assistant-answered", { assistant: m[1] ?? "" })],
  [/^Réponse coupée par (.+)$/, (m) => msg("journal-answer-cut", { name: m[1] ?? "" })],
  [/^Réponse de secours : modèle trop lent$/, () => msg("journal-fallback", { reason: "model_slow" })],
  [/^Outil (\S+) appelé$/, (m) => msg("journal-tool-called", { tool: m[1] ?? "" })],
  [/^Outil (\S+) terminé en (.+)$/, (m) => msg("journal-tool-done", { tool: m[1] ?? "", duration: m[2] ?? "" })],
  [/^Outil (\S+) en échec$/, (m) => msg("journal-tool-failed", { tool: m[1] ?? "" })],
  [/^Tâche (\S+) confiée à (\S+)$/, (m) => msg("journal-task-started", { task: m[1] ?? "", executor: m[2] ?? "" })],
  [/^Tâche (\S+) : nouvelle étape$/, (m) => msg("journal-task-progressed", { task: m[1] ?? "" })],
  [/^Tâche (\S+) terminée \((.+)\)$/, (m) => msg("journal-task-completed", { task: m[1] ?? "", duration: m[2] ?? "" })],
  [/^Tâche (\S+) en échec \((.+)\)$/, (m) => msg("journal-task-failed", { task: m[1] ?? "", duration: m[2] ?? "" })],
  [/^Veille créée : (.+)$/, (m) => msg("journal-watch-created", { what: m[1] ?? "" })],
  [
    /^Veille (\S+) déclenchée par « (.+) »$/,
    (m) => msg("journal-watch-triggered", { watch: m[1] ?? "", item: m[2] ?? "" }),
  ],
  [/^Tri : pertinent, à signaler aujourd'hui$/, () => msg("journal-watch-triaged-urgent")],
  [/^Tri : pertinent pour (.+)$/, (m) => msg("journal-watch-triaged", { name: m[1] ?? "" })],
  [
    /^Décision d(?:e parler|'écrire) à (\S+) — (.+?)( \(relance\))?$/,
    (m) =>
      msg("journal-delivery-considered", {
        name: m[1] ?? "",
        written: m[0].includes("d'écrire") ? "yes" : "no",
        follow_up: m[3] ? "yes" : "no",
        ...subject(m[2] ?? ""),
      }),
  ],
  [
    /^Message transmis (à voix haute|par écrit) — (.+?)( \(relance\))?$/,
    (m) =>
      msg("journal-delivered", {
        spoken: m[1] === "à voix haute" ? "yes" : "no",
        follow_up: m[3] ? "yes" : "no",
        ...subject(m[2] ?? ""),
      }),
  ],
  [
    /^Message non transmis( à voix haute)? — (.+)$/,
    (m) => msg("journal-delivery-failed", { spoken: m[1] ? "yes" : "no", ...subject(m[2] ?? "") }),
  ],
  [/^Connexion (\S+) à réautoriser$/, (m) => msg("journal-connection-needs-reauth", { account: m[1] ?? "" })],
  [
    /^Compte (\S+) connecté \((.+)\)$/,
    (m) => msg("journal-connection-created", { account: m[1] ?? "", service: m[2] ?? "" }),
  ],
  [
    /^Le satellite (\S+) \((.+), pièce « (.+) »\) demande l'appairage$/,
    (m) => msg("journal-pairing-requested", { device: m[1] ?? "", model: m[2] ?? "", room: m[3] ?? "" }),
  ],
  [/^Souvenir enregistré$/, () => msg("journal-memory-recorded")],
];

const REASONS: [RegExp, (m: RegExpMatchArray) => Message][] = [
  [/^(.+) est dans la pièce « (.+) »$/, (m) => msg("reason-in-room", { name: m[1] ?? "", room: m[2] ?? "" })],
  [/^(.+) n'est pas à la maison$/, (m) => msg("reason-away", { name: m[1] ?? "" })],
  [/^aucune information de présence/, () => msg("reason-no-presence")],
  [
    /^pas de réponse depuis (\d+) min, et (.+) n'est pas à la maison$/,
    (m) => msg("reason-no-reply-away", { minutes: Number(m[1]), name: m[2] ?? "" }),
  ],
];

function parse(table: typeof TITLES, text: string): Message {
  for (const [pattern, build] of table) {
    const m = text.match(pattern);
    if (m) return build(m);
  }
  return msg("journal-unknown", { text });
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
  return {
    ...rest,
    message: parse(TITLES, title),
    text: title,
    reason: reason ? { message: parse(REASONS, reason), text: reason } : null,
  };
}

/** The event as the server sends it to an account reading `lang`. */
export function localize<E extends JournalItem | JournalEvent>(event: E, lang: Lang): E {
  return {
    ...event,
    text: event.message.id === "journal-unknown" ? event.text : render(lang, event.message),
    reason: event.reason ? { ...event.reason, text: render(lang, event.reason.message) } : null,
  };
}

export function errorText(lang: Lang, id: string, args: Message["args"] = {}): string {
  return render(lang, { id, args });
}
