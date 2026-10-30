/**
 * The stress fixture: the shapes real data takes (long URLs, unbroken ids, multi-line JSON, long
 * French sentences, provider errors) at extreme lengths, spread over every screen. Synthetic, never
 * real data. On when `localStorage["nestor.mock.stress"]` is set (the overflow guard sets it).
 */
import type { JournalEvent } from "@/api";
import type { Db } from "./db";
import { type Draft, toItem } from "./messages";

export const STRESS_KEY = "nestor.mock.stress";

export function stressed(): boolean {
  try {
    return typeof localStorage !== "undefined" && localStorage.getItem(STRESS_KEY) === "1";
  } catch {
    return false;
  }
}

/** A URL with no space anywhere, about 300 characters long. */
export const LONG_URL = `https://cloud.example.org/remote.php/dav/files/household/Documents/${"administratif-impots-2026-".repeat(8)}declaration-revenus.pdf?token=${"a1b2c3d4e5f6".repeat(4)}`;
/** One 60-character word. */
export const LONG_WORD = "Anticonstitutionnellementdéraisonnablementinextricablement-60";
const JSON_ARGS = JSON.stringify(
  {
    query: `from:${"notifications-automatiques-ne-pas-repondre".repeat(2)}@impots.gouv.example subject:"avis"`,
    folder: "INBOX/Administratif/Impôts/2026/Avis-de-situation-déclarative",
    limit: 50,
    include: ["attachments", "headers", "body"],
  },
  null,
  2,
);
const LONG_SENTENCE =
  "Je n'ai pas pu joindre le serveur de messagerie parce que le fournisseur a répondu avec une erreur inattendue au moment de renouveler le jeton d'accès, et j'ai donc préféré ne rien envoyer plutôt que de risquer un message incomplet ou en double à toute la famille.";
const PROVIDER_ERROR = `invalid_grant: Token has been expired or revoked. (request_id=${"9f8e7d6c5b4a".repeat(5)}) at ${LONG_URL}`;
const LONG_NAME = "Marie-Amélie Bérengère de La Tour d'Auvergne-Lauraguais";
const LONG_ROOM = "chambre-d-amis-du-deuxième-étage-côté-jardin-sous-les-combles";

/** Adds the stress shapes to a fresh mock state. */
export function stress(db: Db, now = Date.now()): void {
  const at = (minutes: number) => new Date(now - minutes * 60_000).toISOString();
  db.people.push({
    id: "marie-amelie",
    name: LONG_NAME,
    channels: ["voice", `telegram:@${"marie_amelie_de_la_tour".repeat(2)}`, "web"],
    reach: `telegram:@${"marie_amelie_de_la_tour".repeat(2)}`,
    presence: { home: true, room: LONG_ROOM, since: at(3) },
    account: null,
    account_login: null,
  });
  const mathis = db.accounts[0];
  if (mathis) mathis.login = `mathis.lambert.${"administrateur-principal".repeat(2)}@example.org`;

  let position = Math.max(0, ...db.journal.map((e) => Number(e.id) || 0));
  const events: JournalEvent[] = [];
  const ev = (d: Partial<Omit<Draft, "title">> & Pick<Draft, "type" | "kind"> & { text: string }, ago: number) => {
    const id = String(++position);
    const { text, ...rest } = d;
    const item = toItem({
      detail: "",
      people: [],
      channels: [],
      room: null,
      tone: "normal",
      links: {},
      cause: null,
      outcome: null,
      tool: null,
      brand: null,
      ...rest,
      title: text,
    });
    events.push({
      ...item,
      id,
      uid: `stress-${id}`,
      at: at(ago),
      kind_label: "",
      record: { type: d.type, payload: { text: d.detail, url: LONG_URL, args: JSON_ARGS } },
    });
  };
  const session = { session: "s-stress", turn: "t-stress" };
  ev(
    {
      type: "conversation.user_turn",
      kind: "conversation",
      text: "Marie-Amélie a dit",
      detail: `Regarde ce document ${LONG_URL} et dis-moi si ${LONG_WORD} apparaît dedans, c'est urgent.`,
      people: ["marie-amelie"],
      channels: ["web"],
      room: LONG_ROOM,
      links: session,
    },
    1.6,
  );
  ev(
    {
      type: "tools.tool_called",
      kind: "tool",
      text: `Outil ${LONG_WORD} appelé`,
      detail: JSON_ARGS,
      tool: LONG_WORD,
      brand: "mcp",
      links: { ...session, call: "c-stress" },
    },
    1.5,
  );
  ev(
    {
      type: "tools.tool_completed",
      kind: "tool",
      text: `Outil ${LONG_WORD} en échec`,
      detail: PROVIDER_ERROR,
      tool: LONG_WORD,
      brand: "mcp",
      tone: "warning",
      outcome: { ok: false, duration_s: 12.4 },
      links: { ...session, call: "c-stress" },
    },
    1.4,
  );
  ev(
    {
      type: "conversation.assistant_turn",
      kind: "conversation",
      text: "Richie a répondu",
      detail: `${LONG_SENTENCE}\n\nLe lien que tu m'as donné : ${LONG_URL}`,
      channels: ["web"],
      links: session,
    },
    1.3,
  );
  ev(
    {
      type: "initiative.delivery_failed",
      kind: "delivery",
      text: `Message non transmis : ${LONG_WORD}`,
      detail: PROVIDER_ERROR,
      people: ["marie-amelie"],
      channels: ["telegram"],
      tone: "warning",
      links: { delivery: "d-stress" },
    },
    1.2,
  );
  db.journal = [...events.reverse(), ...db.journal];

  db.tasks.unshift({
    id: `t-${"0123456789abcdef".repeat(2)}`,
    objective: `${LONG_SENTENCE} Le dossier est ici : ${LONG_URL}`,
    executor: "hermes",
    status: "running",
    status_label: "en cours",
    requested_by: "marie-amelie",
    started_at: at(20),
    ended_at: null,
    steps: [`Téléchargement de ${LONG_URL}`, `Analyse de ${LONG_WORD}`],
    result: null,
    error: PROVIDER_ERROR,
    origin: { session: "s-stress", channel: "web" },
    delivered: null,
  });
  db.watches.unshift({
    id: `w-${"fedcba9876543210".repeat(2)}`,
    what: `Préviens ${LONG_NAME} quand ${LONG_WORD} répond à propos de ${LONG_URL}`,
    owner: "marie-amelie",
    kinds: ["mail"],
    keywords: [LONG_WORD, LONG_URL],
    once: false,
    created_at: at(300),
    until: null,
    origin: { session: "s-stress", channel: "web" },
    triggered: 0,
    last_triggered_at: null,
  });
  db.memories.unshift({
    id: "m-stress",
    text: `${LONG_NAME} range ses papiers sur ${LONG_URL} et appelle ça ${LONG_WORD}.`,
    about: "marie-amelie",
    told_by: "marie-amelie",
    channel: "web",
    updated_at: at(10),
    learnt_event: null,
    session: "s-stress",
    editable: true,
  });
  const connection = db.connections[0];
  if (connection) {
    connection.account = `${"tres.long.identifiant.de.messagerie".repeat(2)}@example-household-provider.org`;
    connection.status = "error";
    connection.status_reason = PROVIDER_ERROR;
  }
  const satellite = db.satellites[0];
  if (satellite) satellite.room = LONG_ROOM;
  const persona = db.config.document.persona as Record<string, unknown>;
  persona.character = `${LONG_SENTENCE} ${LONG_URL}`;
  const tools = db.config.document.tools as Record<string, unknown>[];
  tools.push({ kind: "mcp", name: LONG_WORD, url: LONG_URL, headers: { [`X-${LONG_WORD}`]: "secret-value" } });
  db.config.vault[`tools.${LONG_WORD}.token.${"x".repeat(40)}`] = { value: LONG_WORD, at: at(5) };
}
