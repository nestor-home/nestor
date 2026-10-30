/**
 * The API v1 as Nestor answers it, on the mock state: the same paths, codes and error bodies,
 * every answer built as its generated DTO type (dto.ts) so the mocks cannot drift from the API.
 */
import { delay, HttpResponse, http, type JsonBodyType, sse } from "msw";
import type { Connection, JournalItem } from "@/api";
import type { components } from "@/api/schema.gen";
import * as config from "./config";
import { db, save } from "./db";
import {
  accountDto,
  componentDto,
  connectionDetailDto,
  connectionDto,
  connectorDto,
  invitationDto,
  journalItemDto,
  meDto,
  memoryDto,
  pendingDto,
  personDto,
  satelliteDto,
  taskDto,
  watchDto,
} from "./dto";
import { inEnglish } from "./english";
import { KIND_LABELS, LIVE, ROLE_LABEL, tools as toolsOf } from "./fixtures";
import { facets, filtersOf, matching, withoutRecord } from "./journal";
import { errorText, type Lang, localize, toItem } from "./messages";

type In<N extends keyof components["schemas"]> = components["schemas"][N];

const API = "/api/v1";
const PAGE = 30;
export const CSRF = "mock-csrf-token";

/** The language of this request's answers: the account's, else the browser's, else French. */
let lang: Lang = "fr";

function listen(request: Request): void {
  const account = db.accounts.find((a) => a.id === db.signedIn);
  const asked = request.headers.get("Accept-Language")?.slice(0, 2);
  lang = (account?.locale as Lang | null) ?? (asked === "fr" || asked === "en" ? asked : "fr");
}

/** A JSON answer in the reader's language (static server texts; content stays as written). */
const json = <T extends JsonBodyType>(body: T, init?: ResponseInit) =>
  HttpResponse.json(lang === "en" ? inEnglish(body) : body, init);

const noContent = () => new HttpResponse(null, { status: 204 });

const fail = (status: number, code: string, id: string, args: Record<string, string | number> = {}) =>
  HttpResponse.json({ error: { code, message_id: id, args, message: errorText(lang, id, args) } }, { status });

const NOUNS: Record<string, Record<Lang, string>> = {
  account: { fr: "Compte", en: "Account" },
  event: { fr: "Événement", en: "Event" },
  connector: { fr: "Connecteur", en: "Connector" },
  connection: { fr: "Connexion", en: "Connection" },
  task: { fr: "Tâche", en: "Task" },
  memory: { fr: "Souvenir", en: "Memory" },
  invitation: { fr: "Invitation", en: "Invitation" },
  satellite: { fr: "Satellite", en: "Satellite" },
  watch: { fr: "Veille", en: "Watch" },
};

const notFound = (what: keyof typeof NOUNS) =>
  fail(404, "not_found", "error-resource-not-found", { what: NOUNS[what]?.[lang] ?? what });

const signedIn = () => db.accounts.find((a) => a.id === db.signedIn) ?? null;

/** Every call but sign-in and invitations needs the session; unsafe ones also the CSRF header. */
function guard(request: Request): Response | null {
  listen(request);
  if (restarting()) return HttpResponse.error();
  if (!signedIn()) return fail(401, "unauthenticated", "error-session-expired");
  if (request.method !== "GET" && request.headers.get("X-CSRF-Token") !== CSRF) return fail(403, "csrf", "error-csrf");
  return null;
}

/** While the instance restarts nothing answers; it comes back a little later. */
let downUntil = 0;
const restarting = () => Date.now() < downUntil;
export const RESTART_MS = 2_500;

const owners = () => db.accounts.filter((a) => a.role === "owner" && !a.disabled);

let sequence = 0;
const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}${(sequence++).toString(36)}`;

const kindLabel = (kind: string) => {
  const fr = KIND_LABELS[kind] ?? kind;
  return lang === "en" ? inEnglish(fr) : fr;
};

const itemOut = (item: JournalItem) => journalItemDto(localize(item, lang), kindLabel(item.kind));

/** A new journal entry at the next position, as the stream and the list will send it. */
function journalize(draft: Omit<JournalItem, "id" | "at" | "uid" | "kind_label">): JournalItem {
  const position = Math.max(0, ...db.journal.map((e) => Number(e.id))) + 1;
  const entry: JournalItem = {
    ...draft,
    id: String(position),
    uid: newId("e"),
    at: new Date().toISOString(),
    kind_label: "",
  };
  db.journal.unshift({ ...entry, record: { type: entry.type, version: 1, at: entry.at, ...entry.links } });
  save();
  return entry;
}

export const handlers = [
  // -- session ----------------------------------------------------------------------------------
  http.get(`${API}/me`, async ({ request }) => {
    listen(request);
    if (restarting()) return HttpResponse.error();
    await delay(120);
    const account = signedIn();
    return account ? json(meDto(account, lang)) : fail(401, "unauthenticated", "error-session-expired");
  }),

  http.post(`${API}/session`, async ({ request }) => {
    listen(request);
    await delay(300);
    const { login, password } = (await request.json()) as In<"LoginIn">;
    const account = db.accounts.find((a) => a.login.toLowerCase() === login.trim().toLowerCase());
    if (!account || password !== "nestor") return fail(401, "bad_credentials", "error-bad-credentials");
    if (account.disabled) return fail(403, "disabled", "error-account-disabled");
    db.signedIn = account.id;
    save();
    listen(request);
    return json(meDto(account, lang));
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
    if (!account) return fail(401, "unauthenticated", "error-session-expired");
    account.locale = locale;
    save();
    listen(request);
    return json(meDto(account, lang));
  }),

  http.get(`${API}/i18n`, () =>
    HttpResponse.json({ locales: ["en", "fr"], default: "en", household: "fr" } satisfies In<"LanguagesOut">),
  ),

  // the server's own catalogue is not mocked: the mock renders `text` itself (messages.ts)
  http.get(`${API}/i18n/:locale`, () => new HttpResponse("", { headers: { "Content-Type": "text/plain" } })),

  // -- invitations (no session, no CSRF: same origin only) ---------------------------------------
  http.post(`${API}/invitations/inspect`, async ({ request }) => {
    listen(request);
    await delay(150);
    const { token } = (await request.json()) as In<"InvitationTokenIn">;
    const invitation = db.invitations.find((i) => i.id === token && i.status === "pending");
    if (!invitation) return fail(404, "invitation_unknown", "error-invitation-unknown");
    return json({
      role: invitation.role,
      role_label: invitation.role_label,
      person: invitation.person ? { id: invitation.person, name: invitation.person_name ?? invitation.person } : null,
      expires_at: invitation.expires_at,
    } satisfies In<"InvitationPreview">);
  }),

  http.post(`${API}/invitations/accept`, async ({ request }) => {
    listen(request);
    await delay(300);
    const body = (await request.json()) as In<"InvitationAcceptIn">;
    const invitation = db.invitations.find((i) => i.id === body.token && i.status === "pending");
    if (!invitation) return fail(404, "invitation_unknown", "error-invitation-unknown");
    if (body.password.length < 12) return fail(400, "weak_password", "error-weak-password", { min: 12 });
    if (db.accounts.some((a) => a.login === body.login)) return fail(409, "account_exists", "error-account-exists");
    const account = {
      id: newId("acc"),
      login: body.login,
      role: invitation.role,
      role_label: invitation.role_label,
      person: invitation.person,
      person_name: invitation.person_name,
      locale: lang,
      disabled: false,
      created_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    };
    db.accounts.push(account);
    invitation.status = "accepted";
    invitation.status_label = "acceptée";
    db.signedIn = account.id;
    save();
    return json(meDto(account, lang), { status: 201 });
  }),

  // -- accounts ---------------------------------------------------------------------------------
  http.get(`${API}/accounts`, ({ request }) => guard(request) ?? json(db.accounts.map(accountDto))),
  http.get(`${API}/accounts/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const account = db.accounts.find((a) => a.id === params.id);
    return account ? json(accountDto(account)) : notFound("account");
  }),
  http.get(
    `${API}/invitations`,
    ({ request }) => guard(request) ?? json(db.invitations.filter((i) => i.status === "pending").map(invitationDto)),
  ),

  http.post(`${API}/invitations`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(250);
    const body = (await request.json()) as In<"InvitationIn">;
    const person = db.people.find((p) => p.id === body.person);
    // as the server: a member's or a guest's account belongs to a person of the household
    if ((body.role === "member" || body.role === "guest") && !person) {
      return fail(400, "person_required", "error-invitation-person");
    }
    const invitation = {
      id: newId("inv"),
      role: body.role,
      role_label: ROLE_LABEL[body.role],
      person: person?.id ?? null,
      person_name: person?.name ?? null,
      status: "pending" as const,
      status_label: "en attente",
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    };
    db.invitations.push(invitation);
    save();
    return json(
      {
        invitation: invitationDto(invitation),
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
      return fail(409, "last_owner", "error-last-owner");
    }
    account.role = role;
    account.role_label = ROLE_LABEL[role];
    save();
    return json(accountDto(account));
  }),

  ...(["disable", "enable"] as const).map((action) =>
    http.post(`${API}/accounts/:id/${action}`, async ({ request, params }) => {
      const refused = guard(request);
      if (refused) return refused;
      await delay(200);
      const account = db.accounts.find((a) => a.id === params.id);
      if (!account) return notFound("account");
      if (action === "disable" && account.role === "owner" && owners().length <= 1) {
        return fail(409, "last_owner", "error-last-owner");
      }
      account.disabled = action === "disable";
      save();
      return json(accountDto(account));
    }),
  ),

  // -- household --------------------------------------------------------------------------------
  http.get(`${API}/household/people`, ({ request }) => guard(request) ?? json(db.people.map(personDto))),
  http.get(`${API}/household/people/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const person = db.people.find((p) => p.id === params.id);
    return person ? json(personDto(person)) : fail(404, "person_unknown", "error-person-unknown");
  }),

  // -- journal ----------------------------------------------------------------------------------
  http.get(`${API}/journal/facets`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(120);
    return json(facets(db.journal, filtersOf(new URL(request.url)), db.people, KIND_LABELS));
  }),

  http.get(`${API}/journal/stream`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/journal/:position`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const event = db.journal.find((e) => e.id === params.position);
    if (!event) return notFound("event");
    return json({ item: itemOut(withoutRecord(event)), record: event.record } satisfies In<"JournalEntryOut">);
  }),

  http.get(`${API}/journal`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(200);
    const url = new URL(request.url);
    const before = url.searchParams.get("before");
    const limit = Number(url.searchParams.get("limit") ?? PAGE);
    if (limit < 1 || limit > 200) return fail(422, "invalid", "error-invalid-request");
    let items = matching(db.journal, filtersOf(url));
    if (before) items = items.filter((e) => Number(e.id) < Number(before));
    const page = items.slice(0, limit).map((e) => itemOut(withoutRecord(e)));
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
        agent: { name: db.system.agent.name, status: "online" },
        restart_required: db.config.restart_required,
        pending_changes: db.config.pending_changes,
        components: db.system.components.map(componentDto),
      } satisfies In<"SystemOut">),
  ),

  // -- connectors -------------------------------------------------------------------------------
  http.get(`${API}/connectors`, ({ request }) => guard(request) ?? json(db.connectors.map(connectorDto))),

  http.get(`${API}/connectors/:kind`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const connector = db.connectors.find((c) => c.kind === params.kind);
    return connector ? json(connectorDto(connector)) : notFound("connector");
  }),

  http.put(`${API}/connectors/:kind/client`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(250);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return notFound("connector");
    const body = (await request.json()) as In<"ClientIn">;
    if (!body.client_id.trim() || !body.client_secret.trim()) {
      return fail(400, "client_incomplete", "error-client-incomplete");
    }
    connector.client = { client_id: body.client_id.trim() };
    save();
    return json(connectorDto(connector));
  }),

  http.post(`${API}/connectors/:kind/authorizations`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(400);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return notFound("connector");
    if (!connector.client) return fail(400, "client_missing", "error-client-missing");
    const body = (await request.json()) as In<"AuthorizationIn">;
    // the provider's consent page would come first; the mock connects and sends the browser back
    const connection = plug(connector.kind, body.person ?? null, body.replaces ?? null, {});
    return json({ authorize_url: `/connections/${connection.id}?connected=1` } satisfies In<"AuthorizationOut">);
  }),

  http.post(`${API}/connectors/:kind/connections`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(500);
    const connector = db.connectors.find((c) => c.kind === params.kind);
    if (!connector) return notFound("connector");
    const body = (await request.json()) as In<"SecretsIn">;
    const values = (body.values ?? {}) as Record<string, string>;
    const missing = connector.fields.filter((f) => !f.optional && !values[f.name]?.trim());
    if (missing.length) {
      return fail(400, "fields_missing", "error-fields-missing", { fields: missing.map((f) => f.label).join(", ") });
    }
    if (values.host?.includes("invalide")) return fail(502, "provider_refused", "error-provider-refused");
    const connection = plug(connector.kind, body.person ?? null, body.replaces ?? null, values);
    return json(connectionDetailDto(connection), { status: 201 });
  }),

  // -- connections ------------------------------------------------------------------------------
  http.get(`${API}/connections`, ({ request }) => guard(request) ?? json(db.connections.map(connectionDto))),

  http.get(`${API}/connections/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(150);
    const connection = db.connections.find((c) => c.id === params.id);
    return connection ? json(connectionDetailDto(connection)) : notFound("connection");
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
    }
    save();
    return json(connectionDetailDto(connection));
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
    const now = new Date().toISOString();
    return json({
      pending: db.pairing.filter((p) => p.expires_at > now).map(pendingDto),
      paired: db.satellites.map(satelliteDto),
    } satisfies In<"SatellitesOut">);
  }),

  http.get(`${API}/satellites/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const satellite = db.satellites.find((x) => x.id === params.id);
    return satellite ? json(satelliteDto(satellite)) : notFound("satellite");
  }),

  http.post(`${API}/satellites/approvals`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(400);
    const body = (await request.json()) as In<"ApprovalIn">;
    const pending = db.pairing.find((p) => p.id === body.pairing_id);
    // the mock accepts 424242 as the code every device shows
    if (!pending || body.code !== "424242") return fail(400, "pairing_refused", "error-pairing-refused");
    const approver = signedIn();
    const satellite = {
      id: pending.device.id,
      model: pending.device.model,
      room: pending.device.room,
      capabilities: pending.capabilities.filter((c) => (body.capabilities ?? []).includes(c.name)),
      paired_at: new Date().toISOString(),
      approved_by: approver?.person ?? null,
      approved_by_name: approver?.person_name ?? null,
      connected: true,
      last_seen_at: new Date().toISOString(),
      brand: pending.device.brand,
      sdk: pending.device.sdk,
      sdk_version: null,
    };
    db.pairing = db.pairing.filter((p) => p.id !== pending.id);
    db.satellites.push(satellite);
    save();
    return json(satelliteDto(satellite), { status: 201 });
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
      running: db.tasks.filter((t) => t.status === "running").map(taskDto),
      recent: db.tasks.filter((t) => t.status !== "running").map(taskDto),
    } satisfies In<"TasksOut">);
  }),

  http.get(`${API}/tasks/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const task = db.tasks.find((t) => t.id === params.id);
    return task ? json(taskDto(task)) : notFound("task");
  }),

  http.post(`${API}/tasks/:id/cancel`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(300);
    const task = db.tasks.find((t) => t.id === params.id);
    if (!task) return notFound("task");
    task.status = "cancelled";
    task.status_label = "annulée";
    task.ended_at = new Date().toISOString();
    save();
    return json({ task: taskDto(task), confirmed: true } satisfies In<"CancelOut">);
  }),

  http.get(`${API}/watches`, ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const kinds = [...new Set(db.connectors.flatMap((c) => c.inbound))];
    return json({ watches: db.watches.map(watchDto), kinds } satisfies In<"WatchesOut">);
  }),

  http.get(`${API}/watches/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    const watch = db.watches.find((w) => w.id === params.id);
    return watch ? json(watchDto(watch)) : notFound("watch");
  }),

  http.post(`${API}/watches/:id/cancel`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    db.watches = db.watches.filter((w) => w.id !== params.id);
    save();
    return noContent();
  }),

  http.get(`${API}/memories`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(150);
    const query = new URL(request.url).searchParams;
    const q = query.get("q")?.toLowerCase().trim();
    const about = query.get("about");
    return json(
      db.memories
        .filter((m) => (!q || m.text.toLowerCase().includes(q)) && (!about || m.about === about))
        .map(memoryDto),
    );
  }),

  http.patch(`${API}/memories/:id`, async ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    await delay(200);
    const memory = db.memories.find((m) => m.id === params.id);
    if (!memory) return notFound("memory");
    const { text } = (await request.json()) as In<"CorrectionIn">;
    if (!text.trim()) return fail(400, "empty", "error-memory-empty");
    memory.text = text.trim();
    memory.updated_at = new Date().toISOString();
    save();
    return json(memoryDto(memory));
  }),

  http.delete(`${API}/memories/:id`, ({ request, params }) => {
    const refused = guard(request);
    if (refused) return refused;
    db.memories = db.memories.filter((m) => m.id !== params.id);
    save();
    return noContent();
  }),
  // -- configuration ----------------------------------------------------------------------------
  http.get("/health", () => (restarting() ? HttpResponse.error() : HttpResponse.json({ status: "ok" }))),

  http.post(`${API}/system/restart`, async ({ request }) => {
    const refused = guard(request);
    if (refused) return refused;
    const body = (await request.json()) as In<"RestartIn">;
    if (!body.confirm) return fail(400, "restart_unconfirmed", "error-restart-unconfirmed");
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
    if (!entry) return fail(404, "config_history_unknown", "error-config-history-unknown");
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
    if (!entry) return fail(404, "config_history_unknown", "error-config-history-unknown");
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
    if (!value) return fail(422, "invalid", "error-invalid-request");
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
    if (used.length && !force) return fail(409, "secret_in_use", "error-secret-in-use", { paths: used.join(", ") });
    if (!(name in db.config.vault)) return fail(404, "secret_unknown", "error-secret-unknown");
    delete db.config.vault[name];
    save();
    return noContent();
  }),
];

/** A new connection (replacing a broken one when asked), journaled as the server does. */
function plug(
  kind: string,
  person: string | null,
  replaces: string | null,
  values: Record<string, string>,
): Connection {
  const connector = db.connectors.find((c) => c.kind === kind);
  const replaced = db.connections.find((c) => c.id === replaces);
  const connection: Connection = {
    id: newId("c"),
    kind,
    title: connector?.title ?? kind,
    account:
      values.username ||
      values.name ||
      (connector?.auth === "oauth2" ? `${person ?? "foyer"}@gmail.com` : (connector?.title ?? kind)),
    owner: person,
    status: "connected",
    status_label: "connectée",
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
  journalize(
    toItem({
      type: "connectors.connection_created",
      kind: "connection",
      title: `Compte ${connection.account} connecté (${connection.title})`,
      detail: "",
      people: person ? [person] : [],
      channels: [],
      room: null,
      tone: "normal",
      links: { connection: connection.id },
      cause: null,
      outcome: null,
      tool: null,
      brand: connection.brand,
    }),
  );
  save();
  return connection;
}

/**
 * The live journal: one line from `LIVE` every nine seconds. Built on demand because msw refuses
 * to create an SSE handler where there is no EventSource (Node); tests drive a fake stream instead.
 */
export function liveJournal() {
  return sse<{ item: string }>(`${API}/journal/stream`, ({ client, request }) => {
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
      { error: { code: "config_invalid", message_id: "error-config-invalid", args, message, problems } },
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
