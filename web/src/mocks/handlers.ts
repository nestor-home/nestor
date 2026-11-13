/**
 * The API v1 as Nestor answers it, on the mock state: the same paths, codes and error bodies,
 * its state and every answer typed as the API's generated schemas, so the mocks cannot drift from it.
 */
import { HttpResponse, http, type JsonBodyType, delay as latency, sse } from "msw";
import type { components } from "@/api/schema.gen";
import { answerTo, chatMessage, MENTIONS, type MockChat, mentionedIn } from "./chats";
import * as config from "./config";
import { LIVE } from "./day";
import { db, type MockAddition, save } from "./db";
import { picture, recording } from "./files";
import { arriving, METHODS, type MockPending, type MockPerson, PROTOCOL, SCOPES, tools as toolsOf } from "./fixtures";
import { inFrench } from "./french";
import { facets, filtersOf, matching } from "./journal";
import { catalogueOf, type Draft, errorText, type Lang, localize, render, toItem } from "./messages";

type In<N extends keyof components["schemas"]> = components["schemas"][N];

const API = "/api/v1";

/**
 * A real server's latency, in the browser only: under test it would only slow every render of
 * the whole app and make the waits of parallel test files race against it.
 */
const delay = (ms: number) => (import.meta.env.MODE === "test" ? Promise.resolve() : latency(ms));
const PAGE = 30;
export const CSRF = "mock-csrf-token";

/** The language of this request's answers: the account's, else the browser's, else English. */
let lang: Lang = "en";

function listen(request: Request): void {
  const account = db.accounts.find((a) => a.id === db.signedIn);
  const asked = request.headers.get("Accept-Language")?.slice(0, 2);
  lang = (account?.locale as Lang | null) ?? (asked === "fr" || asked === "en" ? asked : "en");
}

/** A JSON answer in the reader's language: the household's texts follow it (french.ts). */
const json = <T extends JsonBodyType>(body: T, init?: ResponseInit) =>
  HttpResponse.json(lang === "fr" ? inFrench(body) : body, init);

/** The journal as the reader reads it, so that a search or a room filter finds what they see. */
const journal = () => (lang === "fr" ? db.journal.map(inFrench) : db.journal);

const noContent = () => new HttpResponse(null, { status: 204 });

/** An API error as Nestor's `ApiError` writes it: its message is `error-<code with dashes>`. */
const fail = (status: number, code: In<"ErrorDetail">["code"], args: Record<string, string | number> = {}) => {
  const id = `error-${code.replace(/_/g, "-")}`;
  return HttpResponse.json(
    { error: { code, message_id: id, args, message: errorText(lang, id, args) } } satisfies In<"ErrorOut">,
    { status },
  );
};

/** What Nestor answers when a thing is missing, by thing (`not_found` when it says no more). */
const MISSING = {
  account: "not_found",
  event: "journal_entry_unknown",
  attachment: "attachment_unknown",
  connection: "connection_unknown",
  task: "task_unknown",
  memory: "memory_unknown",
  invitation: "invitation_unknown",
  satellite: "satellite_unknown",
  watch: "watch_unknown",
  schedule: "schedule_unknown",
  confirmation: "confirmation_unknown",
} as const;

const notFound = (what: keyof typeof MISSING) => fail(404, MISSING[what]);

const signedIn = () => db.accounts.find((a) => a.id === db.signedIn) ?? null;

/** Every call but sign-in and invitations needs the session; unsafe ones also the CSRF header. */
function guard(request: Request): Response | null {
  listen(request);
  if (restarting()) return HttpResponse.error();
  if (!signedIn()) return fail(401, "unauthenticated");
  if (request.method !== "GET" && request.headers.get("X-CSRF-Token") !== CSRF) return fail(403, "csrf_failed");
  return null;
}

/** How long a mock satellite takes to install a version and come back on it. */
const UPDATE_MS = 4_000;

/** While the instance restarts nothing answers; it comes back a little later. */
let downUntil = 0;

/** Back to a running instance, between tests. */
export function resetServer(): void {
  downUntil = 0;
  recordings.clear();
  for (const timer of pending) clearTimeout(timer);
  pending.clear();
}

/** What the mock server does later (an install, a satellite coming back): never into the next test. */
const pending = new Set<ReturnType<typeof setTimeout>>();
function later(run: () => void, ms: number): void {
  const timer = setTimeout(() => {
    pending.delete(timer);
    run();
  }, ms);
  pending.add(timer);
}
const restarting = () => Date.now() < downUntil;
export const RESTART_MS = 2_500;
export const INSTALL_MS = 3_000; // a release installing, before the restart

const owners = () => db.accounts.filter((a) => a.role === "owner" && !a.disabled);

let sequence = 0;
const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}${(sequence++).toString(36)}`;

/** A person of the mock household as the API names them: `{id, name}`. */
const refOf = (id: string): In<"PersonRef"> => ({ id, name: db.people.find((p) => p.id === id)?.name ?? id });

const itemOut = (item: In<"JournalItem">) => localize(item, lang);

/** A new journal entry at the next position, as the stream and the list will send it. */
function journalize(draft: Draft): In<"JournalItem"> {
  const position = db.journal.reduce((last, e) => Math.max(last, e.item.position), 0) + 1;
  const item = toItem(draft, { position, id: newId("e"), at: new Date().toISOString() });
  db.journal.unshift({ item, record: { type: item.type, version: 1, at: item.at, ...item.links } });
  save();
  return item;
}

// -- what the server composes from its state --------------------------------------------------------

const meOut = (account: In<"AccountOut">): In<"MeOut"> => ({
  account,
  locale: account.locale ?? lang,
  scopes: SCOPES[account.role],
  csrf_token: CSRF,
  assistant: db.system.agent.name,
  agent: { name: db.system.agent.name, status: "started" },
  restart_required: db.config.restart_required,
  pending_changes: db.config.pending_changes,
});

const personOut = ({ account, ...person }: MockPerson): In<"PersonOut"> => ({
  ...person,
  account: db.accounts.find((a) => a.id === account) ?? null,
  connections: db.connections.filter((c) => c.owner?.id === person.id),
});

const connectionDetail = (connection: In<"ConnectionOut">): In<"ConnectionDetail"> => ({
  ...connection,
  tools: db.tools[connection.id] ?? [],
});

const pendingOut = ({ expires_at, ...pending }: MockPending): In<"PendingOut"> => ({
  ...pending,
  expires_in_s: Math.max(0, Math.round((Date.parse(expires_at) - Date.now()) / 1000)),
});

// -- voices -----------------------------------------------------------------------------------------

/** A guided recording in progress, as the mock server keeps it: phrases kept, attempts by phrase. */
interface MockRecording {
  id: string;
  person: string;
  learning: boolean;
  taken: Set<number>;
  attempts: Map<number, number>;
}
const recordings = new Map<string, MockRecording>();
/** How many recordings are open (started, neither finished nor abandoned). */
export const recordingsInProgress = () => recordings.size;
const PHRASES = [1, 2, 3, 4, 5].map((n) => `voice-phrase-${n}`);

/** Their own voice; an owner, the voice of someone without an account (as the server decides). */
function mayManageVoice(person: string): boolean {
  const account = signedIn();
  if (!account) return false;
  if (account.person?.id === person) return true;
  return account.role === "owner" && !db.people.find((p) => p.id === person)?.account;
}

const silentVoice = { enrolled: false, learning: true, learned: 0, enrolled_at: null, last_learned_at: null };

const voiceOut = (person: string): In<"VoiceOut"> => ({
  ...(db.voices[person] ?? silentVoice),
  manageable: mayManageVoice(person),
});

/** The samples of a 16-bit mono WAV at 16 kHz, or null when it is anything else. */
async function wavSeconds(request: Request): Promise<number | null> {
  const body = await request.arrayBuffer();
  if (request.headers.get("Content-Type") !== "audio/wav" || body.byteLength < 44) return null;
  const view = new DataView(body);
  const text = (at: number) => String.fromCharCode(...new Uint8Array(body, at, 4));
  if (text(0) !== "RIFF" || text(8) !== "WAVE" || view.getUint16(20, true) !== 1) return null;
  if (view.getUint16(22, true) !== 1 || view.getUint32(24, true) !== 16_000 || view.getUint16(34, true) !== 16) {
    return null;
  }
  return view.getUint32(40, true) / 2 / 16_000;
}

/** The person a recording is for, when the reader may manage that voice; else the refusal. */
function managedRecording(id: string): MockRecording | Response {
  const recording = recordings.get(id);
  if (!recording) return fail(404, "not_found");
  if (!mayManageVoice(recording.person)) return fail(403, "voice_not_yours");
  return recording;
}

const voiceHandlers = [
  http.get(`${API}/household/people/:id/voice`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    if (!db.people.some((p) => p.id === params.id)) return fail(404, "person_unknown");
    return json(voiceOut(String(params.id)));
  }),

  http.post(`${API}/household/people/:id/voice/recording`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const person = String(params.id);
    if (!db.people.some((p) => p.id === person)) return fail(404, "person_unknown");
    if (!mayManageVoice(person)) return fail(403, "voice_not_yours");
    const { learning } = (await request.json()) as In<"RecordingIn">;
    const id = newId("rec");
    recordings.set(id, { id, person, learning, taken: new Set(), attempts: new Map() });
    return HttpResponse.json(
      {
        id,
        person,
        phrases: PHRASES.map((p) => render(lang, { id: p, args: {} })),
        next: 0,
      } satisfies In<"RecordingOut">,
      { status: 201 },
    );
  }),

  /** Every phrase passes but the second, refused once as too short: the flow shows a retry. */
  http.put(`${API}/voice/recordings/:id/phrases/:n`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const recording = managedRecording(String(params.id));
    if (recording instanceof Response) return recording;
    const phrase = Number(params.n);
    if (!(phrase >= 0 && phrase < PHRASES.length)) return fail(400, "audio_format");
    const seconds = await wavSeconds(request);
    if (seconds === null) return fail(400, "audio_format");
    await delay(400);
    const attempts = (recording.attempts.get(phrase) ?? 0) + 1;
    recording.attempts.set(phrase, attempts);
    const problem = seconds < 0.5 || (phrase === 1 && attempts === 1) ? "too_short" : null;
    if (!problem) recording.taken.add(phrase);
    return json({
      kept: !problem,
      problem,
      taken: recording.taken.size,
      total: PHRASES.length,
    } satisfies In<"PhraseOut">);
  }),

  http.post(`${API}/voice/recordings/:id/finish`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const recording = managedRecording(String(params.id));
    if (recording instanceof Response) return recording;
    if (recording.taken.size < PHRASES.length)
      return fail(400, "invalid", { detail: "some phrases are still missing" });
    await delay(500);
    recordings.delete(recording.id);
    const learned = db.voices[recording.person];
    db.voices[recording.person] = {
      enrolled: true,
      learning: recording.learning,
      learned: learned?.learned ?? 0,
      enrolled_at: new Date().toISOString(),
      last_learned_at: learned?.last_learned_at ?? null,
    };
    save();
    return json(voiceOut(recording.person));
  }),

  http.delete(`${API}/voice/recordings/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const recording = managedRecording(String(params.id));
    if (recording instanceof Response) return recording;
    recordings.delete(recording.id);
    return noContent();
  }),

  /** The voice recorded last is the one recognised, comfortably above the threshold. */
  http.post(`${API}/voice/hear`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    if ((await wavSeconds(request)) === null) return fail(400, "audio_format");
    await delay(300);
    const [person] = Object.entries(db.voices)
      .filter(([, v]) => v.enrolled && v.enrolled_at)
      .sort(([, a], [, b]) => (b.enrolled_at ?? "").localeCompare(a.enrolled_at ?? ""))
      .map(([id]) => id);
    const name = db.people.find((p) => p.id === person)?.name ?? null;
    return json({
      person: person ?? null,
      name,
      score: person ? 0.82 : 0.31,
      threshold: 0.55,
    } satisfies In<"HeardOut">);
  }),

  http.put(`${API}/household/people/:id/voice/learning`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const person = String(params.id);
    if (!mayManageVoice(person)) return fail(403, "voice_not_yours");
    const { learning } = (await request.json()) as In<"LearningIn">;
    db.voices[person] = { ...(db.voices[person] ?? silentVoice), learning };
    save();
    return json(voiceOut(person));
  }),

  http.delete(`${API}/household/people/:id/voice`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const person = String(params.id);
    if (!mayManageVoice(person)) return fail(403, "voice_not_yours");
    await delay(200);
    const voice = db.voices[person];
    if (new URL(request.url).searchParams.get("learned_only") === "true" && voice) {
      db.voices[person] = { ...voice, learned: 0, last_learned_at: null };
    } else delete db.voices[person];
    save();
    return json(voiceOut(person));
  }),
];

// -- the admin's chat ------------------------------------------------------------------------------

const answering = new Map<string, { stopped: boolean }>(); // the chats whose answer is being written
const SESSIONS = "web:mathis/";

const chatOut = (chat: MockChat): In<"ChatOut"> => {
  const first = chat.messages.find((m) => m.role === "person");
  const title = first?.text.replace(/\s+/g, " ").trim() ?? "";
  return {
    id: chat.id,
    title: title.length > 80 ? `${title.slice(0, 79).trimEnd()}…` : title,
    files: first?.files.map((f) => f.kind) ?? [],
    started_at: chat.started_at,
    updated_at: chat.updated_at,
    answering: answering.has(chat.id),
  };
};

/** An answer as the server streams it: one `ChatStreamOut` per line, word by word, `done` last. */
function answer(chat: MockChat, text: string, files: number): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const line = (part: In<"ChatStreamOut">) => encoder.encode(`${JSON.stringify(part)}\n`);
  const turn = `t-${Date.now()}`;
  const reply = answerTo(text, files);
  const said = lang === "fr" ? inFrench(reply.answer) : reply.answer;
  const live = { stopped: false };
  answering.set(chat.id, live);
  return new ReadableStream({
    async start(controller) {
      await delay(700);
      if (reply.tool) {
        chat.messages.push(chatMessage("tool", "", turn, { tool: reply.tool }));
        save();
        await delay(600);
      }
      const words = said.split(/(?<= )/);
      let written = "";
      for (const word of words) {
        if (live.stopped) break;
        written += word;
        controller.enqueue(line({ type: "text", text: word }));
        await delay(35);
      }
      controller.enqueue(line({ type: "end", last: true }));
      chat.messages.push(chatMessage("assistant", written.trim(), turn, { interrupted: live.stopped }));
      chat.updated_at = new Date().toISOString();
      answering.delete(chat.id);
      save();
      controller.enqueue(line({ type: "done" }));
      controller.close();
    },
  });
}

const chatHandlers = [
  http.get(`${API}/chats`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const chats = [...db.chats].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(chatOut);
    return json({ chats, sessions: SESSIONS } satisfies In<"ChatsOut">);
  }),

  http.get(`${API}/chats/mentions`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json(MENTIONS satisfies In<"MentionOut">[]);
  }),

  http.get(`${API}/chats/:chat`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const chat = db.chats.find((c) => c.id === params.chat);
    return json({
      chat: String(params.chat),
      session: `${SESSIONS}${params.chat}`,
      messages: chat?.messages ?? [],
      answering: answering.has(String(params.chat)),
    } satisfies In<"ChatThreadOut">);
  }),

  http.post(`${API}/chats/:chat/messages`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const id = String(params.chat);
    if (answering.has(id)) return fail(409, "chat_busy");
    const body = (await request.json()) as In<"ChatMessageIn">;
    let chat = db.chats.find((c) => c.id === id);
    if (!chat) {
      chat = { id, started_at: new Date().toISOString(), updated_at: new Date().toISOString(), messages: [] };
      db.chats.push(chat);
    }
    const files = (body.files ?? []).map((f, index) => ({
      position: 0,
      index,
      kind: f.kind,
      media_type: f.media_type,
      size: Math.round((f.data.length * 3) / 4),
      name: f.name ?? null,
      transcript: f.kind === "voice" ? (lang === "fr" ? "Allume le salon." : "Turn on the living room.") : null,
    }));
    const said = [body.text ?? "", ...files.map((f) => f.transcript ?? "")].join(" ");
    const mentions = mentionedIn(body.text ?? "");
    chat.messages.push(chatMessage("person", body.text ?? "", `t-${Date.now()}`, { files, mentions }));
    chat.updated_at = new Date().toISOString();
    save();
    return new HttpResponse(answer(chat, said, files.length), { headers: { "Content-Type": "application/x-ndjson" } });
  }),

  http.get(`${API}/chats/:chat/answer`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return noContent(); // the mock's answers are only followed by the page that asked
  }),

  http.post(`${API}/chats/:chat/stop`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const live = answering.get(String(params.chat));
    if (live) live.stopped = true;
    return noContent();
  }),
];

export const handlers = [
  ...voiceHandlers,
  ...chatHandlers,
  // -- session ----------------------------------------------------------------------------------
  http.get(`${API}/me`, async ({ request }) => {
    listen(request);
    if (restarting()) return HttpResponse.error();
    await delay(120);
    const account = signedIn();
    return account ? json(meOut(account)) : fail(401, "unauthenticated");
  }),

  http.post(`${API}/session`, async ({ request }) => {
    listen(request);
    await delay(300);
    const { login, password } = (await request.json()) as In<"LoginIn">;
    const account = db.accounts.find((a) => a.login.toLowerCase() === login.trim().toLowerCase());
    if (!account || password !== "nestor") return fail(401, "invalid_credentials");
    if (account.disabled) return fail(401, "invalid_credentials");
    db.signedIn = account.id;
    save();
    listen(request);
    return json(meOut(account));
  }),

  http.delete(`${API}/session`, () => {
    db.signedIn = null;
    save();
    return noContent();
  }),

  http.put(`${API}/me/locale`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const { locale } = (await request.json()) as In<"LocaleIn">;
    const account = signedIn();
    if (!account) return fail(401, "unauthenticated");
    account.locale = locale;
    save();
    listen(request);
    return json(meOut(account));
  }),

  http.get(`${API}/i18n`, () =>
    HttpResponse.json({ locales: ["en", "fr"], default: "en", household: "en" } satisfies In<"LanguagesOut">),
  ),

  // Nestor's own catalogue, as the server sends it (no plugin adds to it here)
  http.get(`${API}/i18n/:locale`, ({ params }) =>
    params.locale === "en" || params.locale === "fr"
      ? new HttpResponse(catalogueOf(params.locale), { headers: { "Content-Type": "text/plain" } })
      : new HttpResponse(null, { status: 404 }),
  ),

  // -- invitations (no session, no CSRF: same origin only) ---------------------------------------
  http.post(`${API}/invitations/inspect`, async ({ request }) => {
    listen(request);
    await delay(150);
    const { token } = (await request.json()) as In<"InvitationTokenIn">;
    const invitation = db.invitations.find((i) => i.id === token && i.status === "pending");
    if (!invitation) return fail(404, "invitation_unknown");
    return json({
      role: invitation.role,
      person: invitation.person,
      expires_at: invitation.expires_at,
    } satisfies In<"InvitationPreview">);
  }),

  http.post(`${API}/invitations/accept`, async ({ request }) => {
    listen(request);
    await delay(300);
    const body = (await request.json()) as In<"InvitationAcceptIn">;
    const invitation = db.invitations.find((i) => i.id === body.token && i.status === "pending");
    if (!invitation) return fail(404, "invitation_unknown");
    if (body.password.length < 12) return fail(400, "weak_password", { length: 12 });
    if (db.accounts.some((a) => a.login === body.login)) return fail(409, "conflict");
    const account: In<"AccountOut"> = {
      id: newId("acc"),
      login: body.login,
      role: invitation.role,
      person: invitation.person,
      locale: lang,
      disabled: false,
      created_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    };
    db.accounts.push(account);
    invitation.status = "accepted";
    db.signedIn = account.id;
    save();
    return json(meOut(account), { status: 201 });
  }),

  // -- accounts ---------------------------------------------------------------------------------
  http.get(`${API}/accounts`, ({ request }) => guard(request) ?? json(db.accounts)),
  http.get(`${API}/accounts/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const account = db.accounts.find((a) => a.id === params.id);
    return account ? json(account) : notFound("account");
  }),
  http.get(
    `${API}/invitations`,
    ({ request }) => guard(request) ?? json(db.invitations.filter((i) => i.status === "pending")),
  ),

  http.post(`${API}/invitations`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(250);
    const body = (await request.json()) as In<"InvitationIn">;
    const person = db.people.find((p) => p.id === body.person);
    // as the server: a member's or a guest's account belongs to a person of the household
    if ((body.role === "member" || body.role === "guest") && !person) {
      return fail(400, "person_required");
    }
    const invitation: In<"InvitationOut"> = {
      id: newId("inv"),
      role: body.role,
      person: person ? refOf(person.id) : null,
      status: "pending",
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    };
    db.invitations.push(invitation);
    save();
    return json(
      {
        invitation,
        token: invitation.id,
        url: `/invitation/${invitation.id}`,
      } satisfies In<"InvitationCreated">,
      { status: 201 },
    );
  }),

  http.delete(`${API}/invitations/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const invitation = db.invitations.find((i) => i.id === params.id);
    if (!invitation) return notFound("invitation");
    invitation.status = "revoked";
    save();
    return noContent();
  }),

  http.put(`${API}/accounts/:id/role`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(200);
    const account = db.accounts.find((a) => a.id === params.id);
    if (!account) return notFound("account");
    const { role } = (await request.json()) as In<"RoleIn">;
    if (account.role === "owner" && role !== "owner" && owners().length <= 1) {
      return fail(409, "last_owner");
    }
    account.role = role;
    save();
    return json(account);
  }),

  ...(["disable", "enable"] as const).map((action) =>
    http.post(`${API}/accounts/:id/${action}`, async ({ request, params }) => {
      const refused = guard(request);
      if (refused) return refused;
      await delay(200);
      const account = db.accounts.find((a) => a.id === params.id);
      if (!account) return notFound("account");
      if (action === "disable" && account.role === "owner" && owners().length <= 1) {
        return fail(409, "last_owner");
      }
      account.disabled = action === "disable";
      save();
      return json(account);
    }),
  ),

  // -- household --------------------------------------------------------------------------------
  http.get(`${API}/household/people`, ({ request }) => guard(request) ?? json(db.people.map(personOut))),
  http.get(`${API}/household/people/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const person = db.people.find((p) => p.id === params.id);
    return person ? json(personOut(person)) : fail(404, "person_unknown");
  }),

  // -- journal ----------------------------------------------------------------------------------
  http.get(`${API}/journal/facets`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(120);
    const filters = filtersOf(new URL(request.url));
    if (Array.isArray(filters)) return fail(422, "invalid_request", { fields: filters.join(", ") });
    return json(facets(journal(), filters));
  }),

  http.get(`${API}/journal/stream`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/journal/:position/attachments/:index`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const event = db.journal.find((e) => e.item.position === Number(params.position));
    const sent = db.chats.flatMap((c) => c.messages).flatMap((m) => m.files);
    const attachment =
      event?.item.attachments.find((a) => a.index === Number(params.index)) ??
      sent.find((f) => f.position === Number(params.position) && f.index === Number(params.index));
    if (!attachment) return notFound("attachment");
    const [body, type] =
      attachment.kind === "image"
        ? [picture(), "image/png"]
        : attachment.kind === "voice" || attachment.kind === "audio"
          ? [recording(), "audio/wav"]
          : [new TextEncoder().encode("%PDF-1.4\n"), "application/octet-stream"];
    return new HttpResponse(body, { headers: { "Content-Type": type } });
  }),

  http.get(`${API}/journal/:position`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const event = db.journal.find((e) => e.item.position === Number(params.position));
    if (!event) return notFound("event");
    return json({ item: itemOut(event.item), record: event.record } satisfies In<"JournalEntryOut">);
  }),

  http.get(`${API}/journal`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(200);
    const url = new URL(request.url);
    const before = url.searchParams.get("before");
    const limit = Number(url.searchParams.get("limit") ?? PAGE);
    if (limit < 1 || limit > 200) return fail(422, "invalid_request", { fields: "limit" });
    const filters = filtersOf(url);
    if (Array.isArray(filters)) return fail(422, "invalid_request", { fields: filters.join(", ") });
    let items = matching(journal(), filters);
    if (before) items = items.filter((e) => e.position < Number(before));
    const page = items.slice(0, limit).map(itemOut);
    return json({
      items: page,
      next_before: items.length > limit ? (page.at(-1)?.position ?? null) : null,
    } satisfies In<"JournalPage">);
  }),

  // -- system -----------------------------------------------------------------------------------
  http.get(
    `${API}/system`,
    ({ request }) =>
      guard(request) ??
      json({
        nestor: db.system.nestor,
        agent: { name: db.system.agent.name, status: "started" },
        restart_required: db.config.restart_required,
        pending_changes: db.config.pending_changes,
        components: db.system.components,
      } satisfies In<"SystemOut">),
  ),

  http.get(`${API}/system/updates`, ({ request }) => guard(request) ?? json(db.updates satisfies In<"UpdatesOut">)),

  http.post(`${API}/system/updates/install`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const body = (await request.json()) as In<"InstallIn">;
    if (!body.confirm) return fail(400, "update_unconfirmed");
    const updates = db.updates;
    if (!updates.installable || body.version !== updates.releases[0]?.version || updates.installing) {
      return fail(409, "update_not_installable");
    }
    updates.installing = body.version;
    updates.failed = null;
    save();
    // installed a few seconds later, then the restart: everyone signs in again on the new version
    later(() => {
      Object.assign(db.updates, { running: body.version, releases: [], installing: null });
      db.system.nestor.version = body.version;
      db.signedIn = null;
      downUntil = Date.now() + RESTART_MS;
      save();
    }, INSTALL_MS);
    return json(updates satisfies In<"UpdatesOut">, { status: 202 });
  }),

  // -- connectors -------------------------------------------------------------------------------
  http.get(`${API}/connectors`, ({ request }) => guard(request) ?? json(db.connectors)),

  http.get(`${API}/connectors/:kind`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const connector = db.connectors.find((c) => c.kind === params.kind);
    return connector ? json(connector) : fail(404, "connector_unknown", { kind: String(params.kind) });
  }),

  http.put(`${API}/connectors/:kind/client`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(250);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return fail(404, "connector_unknown", { kind: String(params.kind) });
    const body = (await request.json()) as In<"ClientIn">;
    if (!body.client_id.trim() || !body.client_secret.trim()) {
      return fail(400, "client_incomplete");
    }
    if (!connector.oauth) return fail(400, "not_oauth");
    connector.oauth = { ...connector.oauth, registered: true, client_id: body.client_id.trim() };
    save();
    return json(connector);
  }),

  http.post(`${API}/connectors/:kind/authorizations`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(400);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return fail(404, "connector_unknown", { kind: String(params.kind) });
    const body = (await request.json()) as In<"AuthorizationIn">;
    if (connector.auth === "discovered") return discovered(connector, body);
    if (!connector.oauth?.registered) return fail(400, "client_missing");
    // the provider's consent page would come first; the mock connects and sends the browser back
    const connection = plug(connector.kind, body.person ?? null, body.replaces ?? null, {});
    return json({
      authorize_url: `/connections/${connection.id}?connected=1`,
      connection: null,
    } satisfies In<"AuthorizationOut">);
  }),

  http.post(`${API}/connectors/:kind/connections`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(500);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return fail(404, "connector_unknown", { kind: String(params.kind) });
    const body = (await request.json()) as In<"SecretsIn">;
    const values = (body.values ?? {}) as Record<string, string>;
    const missing = connector.fields.filter((f) => f.default === null && !values[f.name]?.trim());
    if (missing.length) {
      return fail(400, "fields_missing", { fields: missing.map((f) => f.label).join(", ") });
    }
    if (values.host?.includes("invalid")) return fail(502, "provider_refused", { detail: "authentication failed" });
    const connection = plug(connector.kind, body.person ?? null, body.replaces ?? null, values);
    return json(connectionDetail(connection), { status: 201 });
  }),

  // -- connections ------------------------------------------------------------------------------
  http.get(`${API}/connections`, ({ request }) => guard(request) ?? json(db.connections)),

  http.get(`${API}/connections/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(150);
    const connection = db.connections.find((c) => c.id === params.id);
    return connection ? json(connectionDetail(connection)) : notFound("connection");
  }),

  http.patch(`${API}/connections/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(250);
    const connection = db.connections.find((c) => c.id === params.id);
    if (!connection) return notFound("connection");
    const body = (await request.json()) as In<"ConnectionSettingsIn">;
    if (body.confirm_writes !== undefined && body.confirm_writes !== null)
      connection.confirm_writes = body.confirm_writes;
    if (body.disabled_tools) {
      const off = new Set(body.disabled_tools);
      db.tools[connection.id] = (db.tools[connection.id] ?? []).map((t) => ({ ...t, enabled: !off.has(t.name) }));
      connection.disabled_tools = [...off];
    }
    save();
    return json(connectionDetail(connection));
  }),

  http.delete(`${API}/connections/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(300);
    db.connections = db.connections.filter((c) => c.id !== params.id);
    save();
    return noContent();
  }),

  // -- satellites -------------------------------------------------------------------------------
  http.get(`${API}/satellites`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    advance();
    const now = new Date().toISOString();
    return json({
      pending: db.pairing.filter((p) => p.expires_at > now).map(pendingOut),
      paired: db.satellites,
      additions: db.additions.filter((a) => a.status === "active").map(additionOut),
    } satisfies In<"SatellitesOut">);
  }),

  http.get(`${API}/satellites/pairing-methods`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json({ methods: METHODS, recommended: "device_code.display" } satisfies In<"MethodsOut">);
  }),

  http.post(`${API}/satellites/additions`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const body = (await request.json()) as In<"AdditionIn">;
    if (body.room !== null && body.room !== undefined && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(body.room))
      return fail(422, "invalid_request", { fields: "room" });
    if (db.additions.filter((a) => a.status === "active").length >= 8) return fail(409, "too_many_additions");
    await delay(250);
    const enrollment = body.method.startsWith("enrollment.");
    const now = Date.now();
    const addition: MockAddition = {
      id: newId("add"),
      method: body.method,
      name: body.name ?? null,
      room: body.room ?? null,
      capabilities: body.capabilities ?? null,
      created_at: new Date(now).toISOString(),
      expires_at: new Date(now + (body.ttl_s ?? 15 * 60) * 1000).toISOString(),
      status: "active",
      device_id: null,
      code: enrollment ? enrollmentCode() : null,
    };
    db.additions.push(addition);
    save();
    const code = addition.code;
    return json(
      {
        addition: additionOut(addition),
        code: code ? `${code.slice(0, 4)}-${code.slice(4)}` : null,
        uri: code ? `nestor+http://nestor.local:8471/?code=${code}` : null,
      } satisfies In<"StartedOut">,
      { status: 201 },
    );
  }),

  http.get(`${API}/satellites/additions`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    advance();
    return json({
      additions: db.additions.filter((a) => a.status === "active").map(additionOut),
    } satisfies In<"AdditionsOut">);
  }),

  http.get(`${API}/satellites/additions/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    advance();
    const addition = db.additions.find((a) => a.id === params.id);
    return addition ? json(additionOut(addition)) : fail(404, "addition_unknown");
  }),

  http.delete(`${API}/satellites/additions/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const addition = db.additions.find((a) => a.id === params.id && a.status === "active");
    if (!addition) return fail(404, "addition_unknown");
    addition.status = "cancelled";
    save();
    return noContent();
  }),

  http.post(`${API}/satellites/pending/:id/identify`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const pending = db.pairing.find((p) => p.pairing_id === params.id);
    if (!pending) return fail(404, "pending_unknown");
    if (!pending.can_identify) return fail(409, "identify_unsupported");
    return noContent();
  }),

  http.post(`${API}/satellites/approvals`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(400);
    const body = (await request.json()) as In<"ApprovalIn">;
    if (!/^\d{6}$/.test(body.code.replace(/\s/g, ""))) return fail(400, "invalid_code");
    const addition = body.addition_id ? db.additions.find((a) => a.id === body.addition_id) : undefined;
    if (body.addition_id && addition?.status !== "active") return fail(409, "addition_over");
    const pending = db.pairing.find((p) => p.pairing_id === body.pairing_id);
    // the mock accepts 424242 as the code every device shows
    if (!pending || body.code.replace(/\s/g, "") !== "424242") return fail(400, "pairing_refused");
    const allowed = body.capabilities ?? addition?.capabilities ?? null;
    const satellite = pair(pending, {
      name: addition?.name ?? null,
      room: addition?.room ?? null,
      capabilities: allowed,
    });
    if (addition) {
      addition.status = "completed";
      addition.device_id = satellite.id;
    }
    save();
    return json(satellite, { status: 201 });
  }),

  http.get(`${API}/satellites/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const satellite = db.satellites.find((x) => x.id === params.id);
    return satellite ? json(satellite) : notFound("satellite");
  }),

  http.post(`${API}/satellites/:id/identify`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const satellite = db.satellites.find((x) => x.id === params.id);
    if (!satellite) return fail(404, "satellite_unknown");
    if (!satellite.can_identify) return fail(409, "identify_unsupported");
    if (!satellite.connected) return fail(409, "satellite_offline");
    return noContent();
  }),

  http.post(`${API}/satellites/:id/update`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const satellite = db.satellites.find((x) => x.id === params.id);
    if (!satellite) return fail(404, "satellite_unknown");
    if (!satellite.can_update) return fail(409, "update_unsupported");
    if (!satellite.connected) return fail(409, "satellite_offline");
    const version = satellite.update?.state === "available" ? satellite.update.version : null;
    if (!version) return fail(409, "update_unavailable");
    satellite.update = { state: "installing", version, notes: satellite.update?.notes ?? null };
    save();
    // it installs, restarts and says hello again on the new version
    later(() => {
      satellite.software = { ...satellite.software, version };
      satellite.update = { state: "current", version: null, notes: null };
      save();
    }, UPDATE_MS);
    return json({ version } satisfies In<"UpdateRequestedOut">, { status: 202 });
  }),

  http.delete(`${API}/satellites/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    db.satellites = db.satellites.filter((s) => s.id !== params.id);
    save();
    return noContent();
  }),

  // -- tasks, watches, memories -----------------------------------------------------------------
  http.get(`${API}/tasks`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json({
      running: db.tasks.filter((t) => t.status === "running"),
      recent: db.tasks.filter((t) => t.status !== "running"),
    } satisfies In<"TasksOut">);
  }),

  http.get(`${API}/tasks/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const task = db.tasks.find((t) => t.id === params.id);
    return task ? json(task) : notFound("task");
  }),

  http.post(`${API}/tasks/:id/cancel`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(300);
    const task = db.tasks.find((t) => t.id === params.id);
    if (!task) return notFound("task");
    task.status = "cancelled";
    task.ended_at = new Date().toISOString();
    save();
    return json({ task, confirmed: true } satisfies In<"CancelOut">);
  }),

  http.get(`${API}/watches`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const kinds = [...new Set(db.connectors.flatMap((c) => c.inbound))];
    return json({ watches: db.watches, kinds } satisfies In<"WatchesOut">);
  }),

  http.get(`${API}/watches/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const watch = db.watches.find((w) => w.id === params.id);
    return watch ? json(watch) : notFound("watch");
  }),

  http.post(`${API}/watches/:id/cancel`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    db.watches = db.watches.filter((w) => w.id !== params.id);
    save();
    return noContent();
  }),

  http.get(`${API}/schedules`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json({ schedules: db.schedules, timezone: "Europe/Paris" } satisfies In<"SchedulesOut">);
  }),

  http.post(`${API}/schedules/:id/cancel`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    if (!db.schedules.some((s) => s.id === params.id)) return notFound("schedule");
    db.schedules = db.schedules.filter((s) => s.id !== params.id);
    save();
    return noContent();
  }),

  http.get(`${API}/messages`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json(db.messages satisfies In<"MessagesOut">);
  }),

  http.get(`${API}/confirmations`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json(db.confirmations satisfies In<"ConfirmationOut">[]);
  }),

  http.post(`${API}/confirmations/:id/answer`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const found = db.confirmations.find((c) => c.id === params.id && c.yours);
    if (!found) return notFound("confirmation");
    const { approved } = (await request.json()) as In<"AnswerIn">;
    db.confirmations = db.confirmations.filter((c) => c.id !== found.id);
    save();
    return json({ approved, result: approved ? "done" : null } satisfies In<"AnsweredOut">);
  }),

  http.get(`${API}/home`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    return json(db.home);
  }),

  http.get(`${API}/memories`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(150);
    const query = new URL(request.url).searchParams;
    const q = query.get("q")?.toLowerCase().trim();
    const about = query.get("about");
    return json(
      db.memories.filter((m) => (!q || m.text.toLowerCase().includes(q)) && (!about || m.about?.id === about)),
    );
  }),

  http.patch(`${API}/memories/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(200);
    const memory = db.memories.find((m) => m.id === params.id);
    if (!memory) return notFound("memory");
    const { text } = (await request.json()) as In<"CorrectionIn">;
    if (!text.trim()) return fail(400, "empty_memory");
    memory.text = text.trim();
    memory.updated_at = new Date().toISOString();
    save();
    return json(memory);
  }),

  http.delete(`${API}/memories/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    db.memories = db.memories.filter((m) => m.id !== params.id);
    save();
    return noContent();
  }),
  // -- the agent --------------------------------------------------------------------------------
  http.get(`${API}/agent/activity`, ({ request }) => guard(request) ?? HttpResponse.json(activityOut())),

  http.get(`${API}/agent/initiative`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const hours = quietOf();
    const soon = new Date(Date.now() + 25 * 60_000).toISOString();
    return HttpResponse.json({
      quiet_hours: hours,
      upcoming: [
        {
          delivery: "watch:w-2b77",
          person: refOf("mathis"),
          spoken_on: "voice:bureau",
          written_on: "telegram:mathis",
          due_at: soon,
        },
      ],
    } satisfies In<"InitiativeOut">);
  }),

  // -- configuration ----------------------------------------------------------------------------
  http.get("/health", () => (restarting() ? HttpResponse.error() : HttpResponse.json({ status: "ok" }))),

  http.post(`${API}/system/restart`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const body = (await request.json()) as In<"RestartIn">;
    if (!body.confirm) return fail(400, "restart_unconfirmed");
    // what a restart applies: the file as written; nothing is pending any more
    const name = (db.config.document.persona as { name?: string } | undefined)?.name;
    if (name) db.system.agent.name = name;
    db.config.restart_required = false;
    db.config.pending_changes = [];
    save();
    downUntil = Date.now() + RESTART_MS;
    db.signedIn = null; // sessions live in the process's memory: everyone signs in again
    return json({ restarting: true } satisfies In<"RestartOut">, { status: 202 });
  }),

  http.get(`${API}/config/schema`, ({ request }) => guard(request) ?? HttpResponse.json(config.SCHEMAS[lang])),

  http.get(
    `${API}/config`,
    ({ request }) =>
      guard(request) ??
      HttpResponse.json({
        document: config.masked(db.config.document),
        path: db.config.path,
        restart_required: db.config.restart_required,
        pending_changes: db.config.pending_changes,
      } satisfies In<"ConfigOut">),
  ),

  http.post(`${API}/config/preview`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const { document } = (await request.json()) as In<"DocumentIn">;
    await delay(150);
    const { doc, pending } = config.prepared(document, db.config.document);
    const problems = config.problems(db.config, doc, pending, lang);
    return HttpResponse.json({
      valid: !problems.length,
      problems,
      diff: config.diff(db.config.document, doc, pending),
    } satisfies In<"PreviewOut">);
  }),

  http.put(`${API}/config`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const { document } = (await request.json()) as In<"DocumentIn">;
    await delay(300);
    return writeConfig(document);
  }),

  http.get(
    `${API}/config/history`,
    ({ request }) =>
      guard(request) ??
      HttpResponse.json(
        db.config.history.map((h) => ({
          id: h.id,
          at: h.at,
          size: JSON.stringify(h.document).length,
        })) satisfies In<"HistoryEntryOut">[],
      ),
  ),

  http.get(`${API}/config/history/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const entry = db.config.history.find((h) => h.id === params.id);
    if (!entry) return fail(404, "config_history_unknown");
    return HttpResponse.json({
      id: entry.id,
      at: entry.at,
      document: config.masked(entry.document),
    } satisfies In<"HistoryDocumentOut">);
  }),

  http.post(`${API}/config/history/:id/restore`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const entry = db.config.history.find((h) => h.id === params.id);
    if (!entry) return fail(404, "config_history_unknown");
    await delay(300);
    return writeConfig(config.masked(entry.document));
  }),

  http.get(`${API}/config/secrets`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const used = config.usedSecrets(db.config.document);
    const names = [...new Set([...Object.keys(db.config.vault), ...Object.keys(used)])].sort();
    return HttpResponse.json(names.map(secretOut) satisfies In<"SecretOut">[]);
  }),

  http.get(`${API}/config/secrets/:name`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    return HttpResponse.json(secretOut(String(params.name)) satisfies In<"SecretOut">);
  }),

  http.put(`${API}/config/secrets/:name`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const { value } = (await request.json()) as In<"SecretIn">;
    await delay(200);
    if (!value) return fail(422, "invalid_request", { fields: "value" });
    db.config.vault[String(params.name)] = { value, at: new Date().toISOString() };
    save();
    return HttpResponse.json(secretOut(String(params.name)) satisfies In<"SecretOut">);
  }),

  http.delete(`${API}/config/secrets/:name`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const name = String(params.name);
    const used = config.usedSecrets(db.config.document)[name] ?? [];
    const force = new URL(request.url).searchParams.get("force") === "true";
    if (used.length && !force) return fail(409, "secret_in_use", { paths: used.join(", ") });
    if (!(name in db.config.vault)) return fail(404, "secret_unknown");
    delete db.config.vault[name];
    save();
    return noContent();
  }),
];

/** A new connection (replacing a broken one when asked), journaled as the server does. */
/**
 * A server found by its address, as the mock imagines it: one on the local network needs nothing and connects at
 * once; GitHub and Asana register no client, so they need one typed; the others send the browser to consent.
 */
function discovered(connector: In<"ConnectorOut">, body: In<"AuthorizationIn">) {
  const values = Object.fromEntries(Object.entries(body.values ?? {}).map(([k, v]) => [k, v.trim()]));
  if (!values.url) return fail(400, "fields_missing", { fields: connector.fields[0]?.label ?? "url" });
  let host: string;
  try {
    host = new URL(values.url).host;
  } catch {
    return fail(502, "provider_refused", { detail: `'${values.url}' is not the address of a server` });
  }
  const preset = connector.presets.find((p) => new URL(p.values.url ?? "").host === host);
  const local = /^(localhost|127\.|192\.168\.|10\.)/.test(host) || preset?.name === "Hugging Face";
  const ownClient = preset?.name === "GitHub" || preset?.name === "Asana";
  if (!local && !values.token && ownClient && !values.client_id) return fail(400, "client_required");
  const who = body.person ?? "household";
  const connection = plug(connector.kind, body.person ?? null, body.replaces ?? null, { account: `${who}@${host}` });
  connection.brand = preset?.brand ?? connector.brand;
  save();
  if (local || values.token) {
    return json({ authorize_url: null, connection: connectionDetail(connection) } satisfies In<"AuthorizationOut">);
  }
  return json({
    authorize_url: `/connections/${connection.id}?connected=1`,
    connection: null,
  } satisfies In<"AuthorizationOut">);
}

function plug(
  kind: string,
  person: string | null,
  replaces: string | null,
  values: Record<string, string>,
): In<"ConnectionOut"> {
  const connector = db.connectors.find((c) => c.kind === kind);
  const replaced = db.connections.find((c) => c.id === replaces);
  const connection: In<"ConnectionOut"> = {
    id: newId("c"),
    kind,
    title: connector?.title ?? kind,
    account:
      values.account ||
      values.username ||
      values.name ||
      (connector?.auth === "oauth2" ? `${person ?? "household"}@gmail.com` : (connector?.title ?? kind)),
    owner: person ? refOf(person) : null,
    status: "connected",
    status_reason: null,
    confirm_writes: replaced?.confirm_writes ?? true,
    disabled_tools: [],
    created_at: new Date().toISOString(),
    brand: connector?.brand ?? null,
    last_used_at: null,
    calls_today: 0,
    watches: 0,
  };
  db.connections.push(connection);
  db.tools[connection.id] = replaced ? (db.tools[replaced.id] ?? []) : toolsOf(kind);
  if (replaced) db.connections = db.connections.filter((c) => c.id !== replaced.id);
  journalize({
    type: "connection.created",
    title: `Account ${connection.account} connected (${connection.title})`,
    people: connection.owner ? [connection.owner] : [],
    links: { connection: connection.id },
    brand: connection.brand,
  });
  save();
  return connection;
}

/**
 * The live journal: one line from `LIVE` every nine seconds. Built on demand because msw refuses
 * to create an SSE handler where there is no EventSource (Node); tests drive a fake stream instead.
 */
export function liveJournal() {
  return sse<{ item: string; activity: string }>(`${API}/journal/stream`, ({ client, request }) => {
    client.send({ event: "activity", data: JSON.stringify(activityOut()) });
    let turn = 0;
    const timer = setInterval(() => {
      const next = LIVE[turn++ % LIVE.length];
      if (next) client.send({ event: "item", data: JSON.stringify(itemOut(journalize(next))) });
    }, 9_000);
    request.signal.addEventListener("abort", () => clearInterval(timer));
  });
}

function secretOut(name: string): In<"SecretOut"> {
  const kept = db.config.vault[name];
  return {
    name,
    set: Boolean(kept),
    preview: kept ? config.preview(kept.value) : null,
    used_by: config.usedSecrets(db.config.document)[name] ?? [],
  };
}

/** Validated as Nestor does; the previous file goes to the history; a person restarts later. */
function writeConfig(document: In<"DocumentIn">["document"]) {
  const { doc, pending } = config.prepared(document, db.config.document);
  const problems = config.problems(db.config, doc, pending, lang);
  if (problems.length) {
    const args = { count: problems.length };
    const message = errorText(lang, "error-config-invalid", args);
    return HttpResponse.json(
      {
        error: { code: "config_invalid", message_id: "error-config-invalid", args, message, problems },
      } satisfies In<"ErrorOut">,
      { status: 422 },
    );
  }
  const diff = config.diff(db.config.document, doc, pending);
  const now = new Date();
  const stamp = `${now
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.(\d{3})Z$/, "$1")}000Z`;
  db.config.history.unshift({ id: stamp, at: now.toISOString(), document: db.config.document });
  for (const [name, value] of Object.entries(pending)) db.config.vault[name] = { value, at: now.toISOString() };
  db.config.document = doc;
  db.config.pending_changes = [...new Set([...db.config.pending_changes, ...config.changedPaths(diff)])].sort();
  db.config.restart_required = true;
  save();
  return HttpResponse.json({
    diff,
    restart_required: true,
    pending_changes: db.config.pending_changes,
  } satisfies In<"WrittenOut">);
}

/** The quiet hours of the mock file, as `GET /agent/initiative` tells them. */
function quietOf(): In<"QuietHoursOut"> | null {
  const text = (db.config.document.initiative as { quiet_hours?: unknown } | undefined)?.quiet_hours;
  const m = typeof text === "string" ? text.match(/^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$/) : null;
  if (!m?.[1] || !m[2]) return null;
  const [start, end] = [m[1], m[2]];
  const minute = (t: string) => Number(t.split(":")[0]) * 60 + Number(t.split(":")[1]);
  const now = new Date();
  const at = now.getHours() * 60 + now.getMinutes();
  const [from, to] = [minute(start), minute(end)];
  const active = from <= to ? at >= from && at < to : at >= from || at < to;
  return { start, end, timezone: "UTC", active };
}

/** What the agent is doing, from the mock state: working while a task runs, asleep in the quiet hours. */
export function activityOut(): In<"AgentActivityOut"> {
  const tasks = db.tasks.filter((t) => t.status === "running").length;
  const quiet = quietOf()?.active ?? false;
  return {
    state: tasks ? "working" : quiet ? "sleeping" : "idle",
    since: new Date(Date.now() - 12 * 60_000).toISOString(),
    replies: 0,
    tasks,
    listening_rooms: [],
    quiet,
  };
}

/** Seconds after an addition starts when its device turns up, in this mock (none on a real server). */
export const DEVICE_TURNS_UP_S = 4;

/**
 * What happens on the household's network while an addition waits: a device given the enrollment
 * code presents it, or a device turns up asking to be paired with its code.
 */
function advance(now = Date.now()): void {
  for (const a of db.additions) {
    if (a.status !== "active") continue;
    if (Date.parse(a.expires_at) <= now) {
      a.status = "expired";
      continue;
    }
    if (now - Date.parse(a.created_at) < DEVICE_TURNS_UP_S * 1000) continue;
    if (a.code) {
      const satellite = pair(arriving(newId("pair"), a.room), a);
      a.status = "completed";
      a.device_id = satellite.id;
    } else if (!db.pairing.some((p) => p.pairing_id === `pair-for-${a.id}`)) {
      db.pairing.push(arriving(`pair-for-${a.id}`, a.room));
    }
  }
  save();
}

/** Pairs a pending device, with what an addition decided. */
function pair(
  pending: MockPending,
  choice: { name: string | null; room: string | null; capabilities: string[] | null },
): In<"SatelliteOut"> {
  const approver = signedIn();
  const satellite: In<"SatelliteOut"> = {
    id: pending.device.id,
    name: choice.name,
    can_identify: pending.can_identify,
    model: pending.device.model,
    room: choice.room ?? pending.device.room,
    capabilities: choice.capabilities
      ? pending.capabilities.filter((c) => choice.capabilities?.includes(c.name))
      : pending.capabilities,
    paired_at: new Date().toISOString(),
    approved_by: approver?.person ?? null,
    connected: true,
    last_seen_at: new Date().toISOString(),
    brand: pending.device.brand,
    software: pending.software,
    protocol: PROTOCOL,
    can_update: pending.capabilities.some((c) => c.name === "device.update"),
    update: null,
  };
  db.pairing = db.pairing.filter((p) => p.pairing_id !== pending.pairing_id);
  db.satellites = [...db.satellites.filter((s) => s.id !== satellite.id), satellite];
  return satellite;
}

function additionOut(a: MockAddition): In<"AdditionOut"> {
  const method = METHODS.find((m) => m.id === a.method) ?? (METHODS[0] as (typeof METHODS)[number]);
  const candidates =
    a.status === "active" && !a.code
      ? db.pairing.filter((p) => p.pairing_id === `pair-for-${a.id}`).map((p) => p.pairing_id)
      : [];
  const stage =
    a.status === "completed"
      ? "paired"
      : a.status === "cancelled"
        ? "cancelled"
        : a.status === "expired"
          ? "expired"
          : candidates.length
            ? "device_seen"
            : "waiting";
  const creator = db.accounts.find((x) => x.id === db.signedIn);
  return {
    id: a.id,
    method,
    stage,
    name: a.name,
    room: a.room,
    capabilities: a.capabilities ? a.capabilities.map((name) => ({ name, label: name })) : null,
    candidates,
    device_id: a.device_id,
    created_by: creator?.person ?? null,
    created_at: a.created_at,
    expires_at: a.expires_at,
    expires_in_s: a.status === "active" ? Math.max(0, Math.round((Date.parse(a.expires_at) - Date.now()) / 1000)) : 0,
  };
}

/** Eight symbols of Crockford's base32 (no I, L, O, U). */
function enrollmentCode(): string {
  const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  return Array.from({ length: 8 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join("");
}
