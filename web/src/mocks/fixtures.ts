/**
 * A believable household for development and tests: Richie serving the Martin family. Written in
 * English, with the French of each text beside it (`fr`) for an admin read in French.
 */
import type {
  Account,
  Capability,
  Component,
  ConfigDocument,
  Confirmation,
  Connection,
  Connector,
  Executors,
  Home,
  Invitation,
  Memory,
  Messages,
  PairingMethod,
  PairingMethodId,
  PairingRequest,
  Person,
  PersonRef,
  Place,
  Retired,
  Retirement,
  Role,
  Satellite,
  Schedule,
  Scope,
  Service,
  SystemInfo,
  TaskThread,
  TaskTurn,
  Tool,
  Updates,
  Voice,
  Watch,
} from "@/api";
import { scopeValues, shelfValues } from "@/api/schema.gen";
import { isRecord } from "@/features/config/schema";
import { oneOf } from "@/lib/enums";
import { fr } from "./french";
import { document, household, type Plugged, plugged, publicUrl, SCHEMAS } from "./instance";
import { render } from "./messages";
import pluginDocs from "./server/plugin-docs.json";
import grants from "./server/role-scopes.json";

export const ASSISTANT = "Richie";

/** A person as the API names them everywhere: `{id, name}`, the name the configuration file gives them. */
export const ref = (id: string): PersonRef => ({ id, name: NAMES.get(id) ?? id });
const NAMES = new Map(household(document()).map((p) => [p.id, p.name]));

export const minutes = (n: number, from = Date.now()) => new Date(from - n * 60_000).toISOString();
const ahead = (seconds: number) => new Date(Date.now() + seconds * 1000).toISOString();

/** The scopes each role grants (Nestor's `GRANTS`, written by `nestor admin mocks`): what `/me` sends. */
const granted = (scopes: string[]) => scopes.filter((s) => oneOf(scopeValues, s));
export const SCOPES: Record<Role, Scope[]> = {
  owner: granted(grants.owner),
  admin: granted(grants.admin),
  member: granted(grants.member),
  guest: granted(grants.guest),
};

/** The rooms of the house, as Home Assistant names its areas. */
export const LIVING_ROOM = fr("living room", "salon");
export const KITCHEN = fr("kitchen", "cuisine");
export const OFFICE = fr("office", "bureau");
export const HALLWAY = fr("hallway", "entrée");
export const BEDROOM = fr("bedroom", "chambre");
const VERANDA = fr("veranda", "véranda");

/** The rooms Home Assistant knows, with what its sensors say of each: someone, nobody, or `null` without a sensor. */
export const ROOMS = [
  [LIVING_ROOM, fr("Living room", "Salon"), true],
  [KITCHEN, fr("Kitchen", "Cuisine"), false],
  [OFFICE, fr("Office", "Bureau"), null],
  [HALLWAY, fr("Hallway", "Entrée"), false],
  [BEDROOM, fr("Bedroom", "Chambre"), false],
] as const;

/** Voices as recorded: Mathis's, long ago and improved since; nobody else's yet. */
export function voices(): Record<string, Omit<Voice, "manageable">> {
  return {
    mathis: {
      enrolled: true,
      learning: true,
      learned: 12,
      enrolled_at: minutes(9 * 24 * 60),
      last_learned_at: minutes(40),
    },
  };
}

/** People as the mock keeps them: their account by id, composed into `PersonOut` when served. */
export type MockPerson = Omit<Person, "account" | "connections"> & { account: string | null };

/** What the file cannot say of a person: where Home Assistant sees them, and the account they open the admin with. */
const SEEN: Record<string, Pick<MockPerson, "presence" | "account">> = {
  mathis: { presence: { home: true, room: LIVING_ROOM, since: minutes(61) }, account: "acc-mathis" },
  lea: { presence: { home: false, room: null, since: minutes(205) }, account: "acc-lea" },
  jules: { presence: { home: true, room: LIVING_ROOM, since: minutes(2) }, account: null },
};

/** The people of the configuration file, with where they are; someone Home Assistant does not know is nowhere. */
export function people(doc: ConfigDocument): MockPerson[] {
  return household(doc).map((p) => ({
    id: p.id,
    name: p.name,
    channel_accounts: p.accounts,
    reach: p.reach,
    ...(SEEN[p.id] ?? { presence: { home: null, room: null, since: null }, account: null }),
  }));
}

export function accounts(): Account[] {
  const account = (
    id: string,
    login: string,
    role: Role,
    person: string | null,
    locale: string | null,
    disabled: boolean,
    ago: number,
  ): Account => ({
    id,
    login,
    role,
    person: person ? ref(person) : null,
    locale,
    disabled,
    created_at: minutes(ago),
    last_seen_at: disabled ? minutes(60 * 24 * 12) : minutes(login === "mathis" ? 1 : 60 * 20),
  });
  return [
    account("acc-mathis", "mathis", "owner", "mathis", null, false, 60 * 24 * 40),
    account("acc-lea", "lea", "admin", "lea", null, false, 60 * 24 * 38),
    account("acc-camille", "camille", "member", null, null, true, 60 * 24 * 20),
  ];
}

export function invitations(): Invitation[] {
  return [
    {
      id: "inv-odile",
      role: "member",
      person: ref("odile"),
      status: "pending",
      created_at: minutes(60 * 24 * 2),
      expires_at: ahead(60 * 60 * 24 * 5),
    },
  ];
}

/** A text of Nestor's own catalogue, as the server sends it: in English, its French beside it. */
const nestor = (id: string, args: Record<string, string | number> = {}) =>
  fr(render("en", { id, args }), render("fr", { id, args }));
const MAILBOX = fr("Mailbox (IMAP)", "Boîte mail (IMAP)");
const MCP_SERVER = fr("MCP server", "Serveur MCP");
/** The well-known servers the connector offers: the same as the server's catalogue. */
export const MCP_PRESETS = [
  { name: "GitHub", brand: "github", values: { url: "https://api.githubcopilot.com/mcp/" } },
  { name: "Linear", brand: "linear", values: { url: "https://mcp.linear.app/mcp" } },
  { name: "Notion", brand: "notion", values: { url: "https://mcp.notion.com/mcp" } },
  { name: "Todoist", brand: "todoist", values: { url: "https://ai.todoist.net/mcp" } },
  { name: "Atlassian", brand: "atlassian", values: { url: "https://mcp.atlassian.com/v1/mcp" } },
  { name: "Asana", brand: "asana", values: { url: "https://mcp.asana.com/v2/mcp" } },
  { name: "Sentry", brand: "sentry", values: { url: "https://mcp.sentry.dev/mcp" } },
  { name: "Cloudflare", brand: "cloudflare", values: { url: "https://bindings.mcp.cloudflare.com/mcp" } },
  { name: "Stripe", brand: "stripe", values: { url: "https://mcp.stripe.com" } },
  { name: "Vercel", brand: "vercel", values: { url: "https://mcp.vercel.com" } },
  { name: "Canva", brand: "canva", values: { url: "https://mcp.canva.com/mcp" } },
  { name: "Hugging Face", brand: "huggingface", values: { url: "https://huggingface.co/mcp" } },
];

/** The relay OAuth comes back through: the file's default (`admin.relay_url`). */
const RELAY = String(
  (SCHEMAS.en.sections.admin as { properties?: Record<string, { default?: unknown }> }).properties?.relay_url?.default,
);

/** What each connector of the catalogue says of itself; the file decides which are plugged in (`connectors`). */
export function connectors(doc: ConfigDocument): Connector[] {
  const configured = new Set(
    plugged(doc)
      .filter((p) => p.slot === "connector")
      .map((p) => p.plugin),
  );
  return catalogue().filter((c) => configured.has(c.kind));
}

function catalogue(): Connector[] {
  return [
    {
      kind: "google",
      brand: "google",
      title: nestor("connector-google-title"),
      description: nestor("connector-google-description"),
      auth: "oauth2",
      inbound: ["mail"],
      setup: nestor("connector-google-setup"),
      fields: [],
      presets: [],
      oauth: {
        registered: true,
        client_id: "418230-9kq3hc.apps.googleusercontent.com",
        redirect_uri: RELAY,
        relayed: true,
      },
    },
    {
      kind: "microsoft",
      brand: "microsoft",
      title: nestor("connector-microsoft-title"),
      description: nestor("connector-microsoft-description"),
      auth: "oauth2",
      inbound: ["mail"],
      setup: nestor("connector-microsoft-setup"),
      fields: [],
      presets: [],
      oauth: {
        registered: false,
        client_id: null,
        redirect_uri: RELAY,
        relayed: true,
      },
    },
    {
      kind: "dav",
      brand: "dav",
      title: nestor("connector-dav-title"),
      description: nestor("connector-dav-description"),
      auth: "secret",
      inbound: [],
      setup: nestor("connector-dav-setup"),
      fields: [
        { name: "server", label: nestor("connector-dav-field-server"), secret: false, default: null },
        { name: "contacts_server", label: nestor("connector-dav-field-contacts_server"), secret: false, default: "" },
        { name: "username", label: nestor("connector-dav-field-username"), secret: false, default: null },
        { name: "password", label: nestor("connector-dav-field-password"), secret: true, default: null },
      ],
      presets: [],
      oauth: null,
    },
    {
      kind: "imap",
      brand: "imap",
      title: MAILBOX,
      description: fr("Any mailbox over IMAP.", "N'importe quelle boîte mail par IMAP."),
      auth: "secret",
      inbound: ["mail"],
      setup: fr(
        "Use an app password rather than your main password when the provider offers one.",
        "Utilisez un mot de passe d'application plutôt que votre mot de passe principal quand le fournisseur le propose.",
      ),
      fields: [
        {
          name: "host",
          label: fr("IMAP server", "Serveur IMAP"),
          secret: false,
          default: null,
        },
        { name: "port", label: "Port", secret: false, default: "993" },
        {
          name: "username",
          label: fr("Username", "Identifiant"),
          secret: false,
          default: null,
        },
        {
          name: "password",
          label: fr("App password", "Mot de passe d'application"),
          secret: true,
          default: null,
        },
      ],
      presets: [],
      oauth: null,
    },
    {
      kind: "mcp",
      brand: "mcp",
      title: MCP_SERVER,
      description: fr(
        "Any service that publishes a remote MCP server (GitHub, Linear, Notion…): its tools, for the account you connect.",
        "Tout service qui publie un serveur MCP distant (GitHub, Linear, Notion…) : ses outils, pour le compte que vous connectez.",
      ),
      auth: "discovered",
      inbound: [],
      setup: fr(
        `Nestor asks the server how to authorise it: most send you to the service to approve access, then back here.
Give an access token only when the service issues one for this (a GitHub personal access token).
Give an OAuth client only when the server registers none for Nestor: create one at the service, with the redirect address shown.`,
        `Nestor demande au serveur comment l'autoriser : la plupart vous envoient sur le service pour approuver l'accès, puis vous ramènent ici.
Donnez un jeton d'accès seulement si le service en délivre un pour cela (un jeton d'accès personnel GitHub).
Donnez un client OAuth seulement si le serveur n'en enregistre aucun pour Nestor : créez-en un sur le service, avec l'adresse de redirection affichée.`,
      ),
      fields: [
        { name: "url", label: fr("Server address", "Adresse du serveur"), secret: false, default: null },
        { name: "token", label: fr("Access token", "Jeton d'accès"), secret: true, default: "" },
        { name: "client_id", label: fr("OAuth client ID", "Identifiant du client OAuth"), secret: false, default: "" },
        {
          name: "client_secret",
          label: fr("OAuth client secret", "Secret du client OAuth"),
          secret: true,
          default: "",
        },
      ],
      presets: MCP_PRESETS,
      oauth: {
        registered: false,
        client_id: null,
        redirect_uri: RELAY,
        relayed: true,
      },
    },
  ];
}

/** Why a connection needs a look, as the server words it: a message and its text. */
const reason = (text: string) => ({ message: { id: "connection-status-reason", args: {} }, text });

const GOOGLE = nestor("connector-google-title");
const MICROSOFT = nestor("connector-microsoft-title");

/** A connected account, unused today unless said. */
const quiet = (
  c: Omit<Connection, "status" | "status_reason" | "disabled_tools" | "calls_today"> & { calls_today?: number },
): Connection => ({
  status: "connected",
  status_reason: null,
  disabled_tools: [],
  calls_today: 0,
  ...c,
});

export function connections(): Connection[] {
  return [
    {
      id: "c-gmail-mathis",
      kind: "google",
      brand: "google",
      title: GOOGLE,
      account: "mathis@example.com",
      owner: ref("mathis"),
      status: "needs_reauth",
      status_reason: reason(
        fr(
          "Google refused to renew the token (invalid_grant).",
          "Google a refusé le renouvellement du jeton (invalid_grant).",
        ),
      ),
      confirm_writes: true,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 21),
      last_used_at: minutes(171),
      calls_today: 2,
      watches: 1,
    },
    {
      id: "c-imap-lea",
      kind: "imap",
      brand: "imap",
      title: MAILBOX,
      account: "lea@martin.family",
      owner: ref("lea"),
      status: "connected",
      status_reason: null,
      confirm_writes: true,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 9),
      last_used_at: minutes(230),
      calls_today: 0,
      watches: 1,
    },
    {
      id: "c-mcp-ha",
      kind: "mcp",
      brand: "mcp",
      title: MCP_SERVER,
      account: "household@homeassistant.local:8123",
      owner: null,
      status: "connected",
      status_reason: null,
      confirm_writes: false,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 30),
      last_used_at: minutes(61),
      calls_today: 1,
      watches: 0,
    },
    {
      id: "c-mcp-recipes",
      kind: "mcp",
      brand: "mcp",
      title: MCP_SERVER,
      account: "lea@192.168.1.20:8808",
      owner: ref("lea"),
      status: "error",
      status_reason: reason(
        fr(
          "Connection refused by http://192.168.1.20:8808/mcp.",
          "Connexion refusée par http://192.168.1.20:8808/mcp.",
        ),
      ),
      confirm_writes: true,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 3),
      last_used_at: minutes(6),
      calls_today: 1,
      watches: 0,
    },
    // Léa's two Google accounts: tools of the second are numbered, and a message names each by its address
    quiet({
      id: "c-google-lea",
      kind: "google",
      brand: "google",
      title: GOOGLE,
      account: "lea.martin@gmail.com",
      owner: ref("lea"),
      confirm_writes: true,
      created_at: minutes(60 * 24 * 12),
      last_used_at: minutes(398),
      watches: 0,
    }),
    quiet({
      id: "c-google-lea-studio",
      kind: "google",
      brand: "google",
      title: GOOGLE,
      account: "lea@studio-martin.fr",
      owner: ref("lea"),
      confirm_writes: true,
      created_at: minutes(60 * 24 * 5),
      last_used_at: minutes(489),
      calls_today: 2,
      watches: 0,
    }),
    quiet({
      id: "c-microsoft-mathis",
      kind: "microsoft",
      brand: "microsoft",
      title: MICROSOFT,
      account: "mathis.martin@outlook.com",
      owner: ref("mathis"),
      confirm_writes: true,
      created_at: minutes(60 * 24 * 8),
      last_used_at: minutes(443),
      calls_today: 1,
      watches: 0,
    }),
    quiet({
      id: "c-dav-family",
      kind: "dav",
      brand: "dav",
      title: nestor("connector-dav-title"),
      account: "famille.martin@icloud.com",
      owner: null,
      confirm_writes: true,
      created_at: minutes(60 * 24 * 40),
      last_used_at: minutes(60 * 20),
      watches: 0,
    }),
    quiet({
      id: "c-mcp-linear",
      kind: "mcp",
      brand: "linear",
      title: MCP_SERVER,
      account: "mathis@mcp.linear.app",
      owner: ref("mathis"),
      confirm_writes: true,
      created_at: minutes(60 * 24 * 2),
      last_used_at: minutes(60 * 22),
      watches: 0,
    }),
  ];
}

/** What each kind of account gives access to, as its connector declares it: a name and its mark. */
const SERVICES: Record<string, [string, string | null][]> = {
  google: [
    ["gmail", "gmail"],
    ["calendar", "google-calendar"],
    ["drive", "google-drive"],
    ["contacts", null],
    ["tasks", "google-tasks"],
  ],
  microsoft: [
    ["outlook", null],
    ["calendar", null],
    ["onedrive", null],
    ["todo", null],
  ],
  dav: [
    ["calendar", null],
    ["contacts", null],
  ],
  imap: [["mail", "imap"]],
};

/** How a message names each remote MCP server: its service's name when well known, else its host's. */
const MCP_SERVICES: Record<string, string> = {
  "c-mcp-ha": "homeassistant",
  "c-mcp-linear": "linear",
  "c-mcp-recipes": "recipes",
};

/**
 * What an account gives access to, as a message names it, the way the server names it: the service alone, or with
 * the start of the address when its person can use another account with that service; none while not connected.
 */
export function services(connection: Connection, all: readonly Connection[]): Service[] {
  const declared = (c: Connection): [string, string | null][] =>
    SERVICES[c.kind] ?? [[MCP_SERVICES[c.id] ?? "mcp", null]];
  const usable = all.filter(
    (c) => c.status === "connected" && (c.owner === null || c.owner?.id === connection.owner?.id),
  );
  return declared(connection).map(([name, brand]) => {
    const alone = usable.filter((c) => declared(c).some(([other]) => other === name)).length === 1;
    const local = connection.account.split("@")[0] ?? "";
    return {
      name,
      brand: brand ?? connection.brand,
      handle: connection.status !== "connected" ? null : alone ? name : `${name}-${local}`,
    };
  });
}

/** A connector's tool as the server lists it: its description is the model's, in English. */
const tool = (name: string, description: string, risk: Tool["risk"] = "read"): Tool => ({
  name,
  description,
  risk,
  enabled: true,
});

export function tools(kind: string, brand: string | null = null): Tool[] {
  if (brand === "linear") {
    return [
      tool("linear_list_issues", "List issues in the user's Linear workspace."),
      tool("linear_get_issue", "Retrieve a Linear issue by its id."),
      tool("linear_create_issue", "Create a new Linear issue.", "write"),
    ];
  }
  if (kind === "google") {
    return [
      tool(
        "google_mail_search",
        "Search the person's Gmail with Gmail query syntax (from:, subject:, newer_than:7d…).",
      ),
      tool("google_mail_read", "Read one Gmail message by id (from google_mail_search): headers and plain-text body."),
      tool("google_calendar_events", "List the events of the person's Google Calendar between two moments."),
      tool("google_calendar_create", "Add an event to the person's Google Calendar.", "write"),
      tool("google_drive_search", "Search the person's Google Drive for files whose name or content contains words."),
      tool("google_drive_read", "Read the text of one Google Drive file by id (from google_drive_search)."),
      tool("google_contacts_search", "Find people in the person's Google Contacts by name, email, phone or company."),
      tool("google_tasks_list", "List the open tasks of the person's Google Tasks."),
      tool("google_tasks_add", "Add a task to the person's Google Tasks.", "write"),
      { ...tool("google_tasks_complete", "Tick off one of the person's Google Tasks by id.", "write"), enabled: false },
    ];
  }
  if (kind === "microsoft") {
    return [
      tool(
        "outlook_mail_search",
        "Search the person's Outlook mail with words (from:, subject: and received: work too).",
      ),
      tool("outlook_mail_read", "Read one Outlook message by id (from outlook_mail_search)."),
      tool("outlook_calendar_events", "List the events of the person's Outlook calendar between two moments."),
      tool("outlook_calendar_create", "Add an event to the person's Outlook calendar.", "write"),
      tool("onedrive_search", "Search the person's OneDrive for files whose name or content contains words."),
      tool("onedrive_read", "Read the text of one OneDrive file by id (from onedrive_search)."),
      tool("todo_list", "List the open tasks of the person's Microsoft To Do."),
      tool("todo_add", "Add a task to the person's Microsoft To Do.", "write"),
      tool("todo_complete", "Tick off one of the person's Microsoft To Do tasks by id.", "write"),
    ];
  }
  if (kind === "dav") {
    return [
      tool("dav_calendar_events", "List the events of the person's calendars (CalDAV) between two moments."),
      tool("dav_calendar_create", "Add an event to one of the person's calendars (CalDAV).", "write"),
      tool("dav_contacts_search", "Find people in the person's contacts (CardDAV) by name, email, phone or company."),
    ];
  }
  if (kind === "imap") {
    return [
      {
        name: "mail_search",
        description: fr(
          "Search emails by sender, subject or date.",
          "Chercher des courriels par expéditeur, sujet ou date.",
        ),
        risk: "read",
        enabled: true,
      },
      {
        name: "mail_read",
        description: fr("Read an email and its text attachments.", "Lire un courriel et ses pièces jointes texte."),
        risk: "read",
        enabled: true,
      },
      {
        name: "mail_draft",
        description: fr("Draft a reply without sending it.", "Préparer un brouillon de réponse, sans l'envoyer."),
        risk: "write",
        enabled: true,
      },
      {
        name: "mail_label",
        description: fr("File an email (labels, archive).", "Classer un courriel (libellés, archivage)."),
        risk: "write",
        enabled: false,
      },
      {
        name: "mail_send",
        description: fr("Send an email on the person's behalf.", "Envoyer un courriel au nom de la personne."),
        risk: "sensitive",
        enabled: false,
      },
    ];
  }
  return [
    {
      name: "ha_get_state",
      description: fr("Read the state of a device or sensor.", "Lire l'état d'un appareil ou d'un capteur."),
      risk: "read",
      enabled: true,
    },
    {
      name: "ha_list_areas",
      description: fr("List the rooms and their devices.", "Lister les pièces et leurs appareils."),
      risk: "read",
      enabled: true,
    },
    {
      name: "ha_turn_on",
      description: fr("Turn on a light, a plug or a scene.", "Allumer une lumière, une prise ou une scène."),
      risk: "write",
      enabled: true,
    },
    {
      name: "ha_turn_off",
      description: fr("Turn off a light, a plug or a scene.", "Éteindre une lumière, une prise ou une scène."),
      risk: "write",
      enabled: true,
    },
    {
      name: "ha_unlock",
      description: fr("Unlock a smart lock.", "Déverrouiller une serrure connectée."),
      risk: "sensitive",
      enabled: false,
    },
  ];
}

const cap = (name: string, label: string): Capability => ({ name, label });
const MIC = cap("audio.capture", fr("microphone", "micro"));
const SPEAKER = cap("audio.playback", fr("speaker", "haut-parleur"));
const VAD = cap("audio.speech_activity", fr("speech detection", "détection de parole"));
const PEOPLE = cap(
  "vision.person_detection",
  fr("person detection (no image sent)", "détection de personnes (sans image transmise)"),
);
const CAMERA = cap("video.capture", fr("camera", "caméra"));
const FACE = cap("expression.emotion", fr("expressions", "expressions"));
const HEAD = cap("motion.head", fr("head movements", "mouvements de tête"));

const IDENTIFY = cap(
  "device.identify",
  fr("identify (light, motion or sound)", "se signaler (lumière, mouvement ou son)"),
);
const UPDATE = cap("device.update", fr("update itself", "se mettre à jour"));

/** The wire format satellites speak, and the software the Reachys run. */
export const PROTOCOL = "nestor.satellite/1";
const REACHY_SOFTWARE = { name: "nestor-reachy", version: "0.4.0" };

/** The pairing methods, as Nestor's catalogue words them (`labels.ftl`), in the recommended order. */
export const METHODS: PairingMethod[] = [
  {
    id: "device_code.display",
    proof: "device_code",
    label: fr("Code on its screen", "Code sur son écran"),
    hint: fr("Type the code the device shows.", "Saisissez le code affiché par l'appareil."),
  },
  {
    id: "device_code.speech",
    proof: "device_code",
    label: fr("Code said aloud", "Code dit à voix haute"),
    hint: fr("Type the code the device says.", "Saisissez le code que dit l'appareil."),
  },
  {
    id: "enrollment.qr",
    proof: "enrollment_code",
    label: "QR code",
    hint: fr("Show the QR code to the device's camera.", "Montrez le QR code à la caméra de l'appareil."),
  },
  {
    id: "enrollment.input",
    proof: "enrollment_code",
    label: fr("Code typed on the device", "Code saisi sur l'appareil"),
    hint: fr("Type this code on the device.", "Saisissez ce code sur l'appareil."),
  },
  {
    id: "enrollment.provisioning",
    proof: "enrollment_code",
    label: "Configuration",
    hint: fr(
      "Give the device the pairing address, in NESTOR_PAIRING_URI or its settings.",
      "Donnez à l'appareil l'adresse d'appairage, dans NESTOR_PAIRING_URI ou ses réglages.",
    ),
  },
];
const method = (id: PairingMethodId) => METHODS.find((m) => m.id === id) as PairingMethod;

/** A device waiting to pair, as the mock keeps it: its deadline, sent as the seconds left. */
export type MockPending = Omit<PairingRequest, "expires_in_s"> & { expires_at: string };

export function pairing(): MockPending[] {
  return [
    {
      pairing_id: "pair-7f3a",
      device: { id: "reachy-mini-hallway", model: "Reachy Mini", room: HALLWAY, brand: "reachy" },
      software: REACHY_SOFTWARE,
      capabilities: [MIC, SPEAKER, VAD, PEOPLE, FACE, HEAD, IDENTIFY],
      methods: [method("device_code.speech"), method("enrollment.provisioning")],
      recommended_method: "device_code.speech",
      can_identify: true,
      expires_at: ahead(4 * 60 + 12),
    },
    {
      pairing_id: "pair-91c0",
      device: { id: "esp32-kitchen", model: "ESP32-S3 Box", room: KITCHEN, brand: "espressif" },
      software: { name: "nestor-satellite", version: "0.5.1" },
      capabilities: [MIC, SPEAKER],
      methods: [method("device_code.display"), method("enrollment.input"), method("enrollment.provisioning")],
      recommended_method: "device_code.display",
      can_identify: false,
      expires_at: ahead(8 * 60 + 40),
    },
  ];
}

/** A device turning up for an addition made with a device code method. */
export function arriving(pairingId: string, room: string | null): MockPending {
  return {
    pairing_id: pairingId,
    device: {
      id: "reachy-mini-veranda",
      model: "Reachy Mini",
      room: room ?? VERANDA,
      brand: "reachy",
    },
    software: REACHY_SOFTWARE,
    capabilities: [MIC, SPEAKER, VAD, FACE, HEAD, IDENTIFY],
    methods: [method("device_code.speech"), method("enrollment.provisioning")],
    recommended_method: "device_code.speech",
    can_identify: true,
    expires_at: ahead(10 * 60),
  };
}

/** No privacy rule: a camera films whenever someone allowed asks, until the household sets one. */
export const NO_RULE = (): Satellite["access"]["privacy"] => ({ quiet: [], off_when_home: false, home_people: [] });

export function satellites(): Satellite[] {
  return [
    {
      id: "reachy-living-room",
      name: fr("Living room Reachy", "Reachy du salon"),
      can_identify: true,
      model: "Reachy Mini",
      room: LIVING_ROOM,
      capabilities: [MIC, SPEAKER, VAD, CAMERA, PEOPLE, FACE, HEAD, UPDATE],
      films: true,
      calls: true,
      paired_at: minutes(60 * 24 * 26),
      approved_by: ref("mathis"),
      connected: true,
      last_seen_at: minutes(0.2),
      brand: "reachy",
      software: { name: "nestor-reachy", version: "0.4.0" },
      protocol: PROTOCOL,
      can_update: true,
      update: {
        state: "available",
        version: "0.4.1",
        notes: "https://github.com/nestor-home/nestor-reachy/releases/tag/v0.4.1",
      },
      access: { viewers: [ref("lea")], callers: [ref("jules"), ref("lea")], camera: true, privacy: NO_RULE() },
    },
    {
      id: "reachy-office",
      name: null,
      can_identify: true,
      model: "Reachy Mini",
      room: OFFICE,
      capabilities: [MIC, SPEAKER, VAD, CAMERA, FACE],
      films: true,
      calls: true,
      paired_at: minutes(60 * 24 * 20),
      approved_by: ref("mathis"),
      connected: false,
      last_seen_at: minutes(97),
      brand: "reachy",
      software: { name: "nestor-reachy", version: "0.4.0" },
      protocol: PROTOCOL,
      can_update: false,
      update: null,
      access: { viewers: [], callers: [], camera: false, privacy: NO_RULE() },
    },
    {
      id: "pi-bedroom",
      name: fr("Jules's speaker", "Enceinte de Jules"),
      can_identify: false,
      model: "Raspberry Pi 5 · ReSpeaker",
      room: BEDROOM,
      capabilities: [MIC, SPEAKER],
      films: false,
      calls: true,
      paired_at: minutes(60 * 24 * 12),
      approved_by: ref("lea"),
      connected: true,
      last_seen_at: minutes(0.5),
      brand: "raspberry-pi",
      software: { name: "nestor-satellite", version: "0.5.1" },
      protocol: PROTOCOL,
      can_update: true,
      update: { state: "current", version: null, notes: null },
      access: { viewers: [], callers: [ref("lea")], camera: true, privacy: NO_RULE() },
    },
  ];
}

/** What the tasks are about, also written in the journal. */
export const CLAIM_TITLE = fr("Glasses insurance claim", "Remboursement des lunettes");
export const CLAIM = fr(
  "Prepare the health insurance claim for Jules's glasses.",
  "Préparer le dossier de remboursement de la mutuelle pour les lunettes de Jules.",
);
export const CLAIM_STEPS = [
  fr("Insurance claim form downloaded.", "Formulaire de la mutuelle téléchargé."),
  fr("Prescription found in Mathis's mail.", "Ordonnance trouvée dans les mails de Mathis."),
];
export const CLAIM_QUESTION = fr(
  "I can't find the optician's invoice. Can you send me a photo of it, or tell me which mailbox it went to?",
  "Je ne trouve pas la facture de l'opticien. Pouvez-vous m'en envoyer une photo, ou me dire dans quelle boîte elle est arrivée ?",
);
export const CLAIM_NOTE = fr(
  "Jules's insurance number is on the September statement.",
  "Le numéro d'adhérent de Jules est sur le relevé de septembre.",
);
export const SHOPPING_TITLE = fr("Week's shopping list", "Liste de courses de la semaine");
export const SHOPPING = fr(
  "Make the week's shopping list from Léa's menus.",
  "Préparer la liste de courses de la semaine à partir des menus de Léa.",
);
export const SHOPPING_STEP = fr(
  "Reading the “Léa's recipes” MCP server.",
  "Lecture du serveur MCP « Recettes de Léa ».",
);
export const SHOPPING_STEER = fr("Group it by aisle, please.", "Regroupe-la par rayon, s'il te plaît.");
export const ENERGY_TITLE = fr("Green electricity offers", "Offres d'électricité verte");
export const ENERGY = fr(
  "Compare three green electricity offers and sum up the yearly price gaps.",
  "Comparer trois offres d'électricité verte et résumer les écarts de prix annuels.",
);
export const ENERGY_STEPS = [
  fr("Read the last two bills.", "Lecture des deux dernières factures."),
  fr("Price lists of the three suppliers fetched.", "Grilles tarifaires des trois fournisseurs récupérées."),
  fr("Worked out over a year, standing charge included.", "Calcul sur un an, abonnement compris."),
];
export const ENERGY_RESULT = fr(
  "The second offer is the cheapest over a year, standing charge included; the third, the most expensive.",
  "La deuxième offre est la moins chère sur un an, abonnement compris ; la troisième, la plus chère.",
);
export const ENERGY_FOLLOW_UP = fr(
  "And with off-peak hours? The washing machine and the dishwasher run at night.",
  "Et avec les heures creuses ? Le lave-linge et le lave-vaisselle tournent la nuit.",
);
export const ENERGY_OFF_PEAK = fr(
  "With off-peak hours, the second offer is still the cheapest: about €64 less a year than today. The first one comes close only if more than half of the use is at night.",
  "Avec les heures creuses, la deuxième offre reste la moins chère : environ 64 € de moins par an qu'aujourd'hui. La première ne s'en approche que si plus de la moitié de la consommation a lieu la nuit.",
);
export const ENERGY_NOTES = [
  fr("Current contract: 9 kVA, base option.", "Contrat actuel : 9 kVA, option base."),
  fr(
    "Yearly use: 4,820 kWh, from the last twelve bills.",
    "Consommation annuelle : 4 820 kWh, d'après les douze dernières factures.",
  ),
];
export const ENERGY_OFF_PEAK_STEP = fr(
  "Off-peak prices of the three suppliers fetched.",
  "Prix en heures creuses des trois fournisseurs récupérés.",
);
export const GYM_ERROR = fr(
  "The site asks for a sign-in by text message: impossible without Léa.",
  "Le site demande une connexion par SMS : impossible sans Léa.",
);

export const DEPENDENCIES_TITLE = fr("Dashboard dependencies", "Dépendances du tableau de bord");
export const DEPENDENCIES = fr(
  "Update the home dashboard's dependencies and say what changed.",
  "Mettre à jour les dépendances du tableau de bord de la maison et dire ce qui a changé.",
);
export const DEPENDENCIES_RESULT = fr(
  "12 dependencies updated, tests green. The report and a capture of the dashboard are attached.",
  "12 dépendances mises à jour, tests au vert. Le rapport et une capture du tableau de bord sont joints.",
);

type TurnFile = TaskTurn["files"][number];
const handed = (index: number, name: string, media_type: string, size: number, kind: TurnFile["kind"] = "file") =>
  ({ index, name, kind, media_type, size, given: false }) satisfies TurnFile;
const given = (file: TurnFile): TurnFile => ({ ...file, given: true });

/** What the tasks were sent and handed back, as a turn lists them (the journal's lines carry the same files). */
export const ENERGY_BILLS: TaskTurn["files"] = [
  given(handed(0, "bill-september.pdf", "application/pdf", 61_400)),
  given(handed(1, "bill-august.pdf", "application/pdf", 59_800)),
];
export const ENERGY_FILES: TaskTurn["files"] = [handed(2, "energy-offers.pdf", "application/pdf", 48_200)];
export const ENERGY_OFF_PEAK_FILES: TaskTurn["files"] = [
  handed(0, "energy-offers-off-peak.pdf", "application/pdf", 51_900),
];
export const DEPENDENCIES_FILES: TaskTurn["files"] = [
  handed(0, "report.md", "text/markdown", 3_412),
  handed(1, "dashboard.png", "image/png", 182_400, "image"),
];
export const CLAIM_FILES: TaskTurn["files"] = [handed(0, "claim-form.pdf", "application/pdf", 88_300)];

/** A turn as the task API sends it: what is not said did not happen. */
function turn(
  draft: Pick<TaskTurn, "id" | "instruction" | "by" | "status" | "started_at"> & Partial<TaskTurn>,
): TaskTurn {
  return {
    ended_at: null,
    steps: [],
    result: null,
    question: null,
    error: null,
    files: [],
    delivered: null,
    steered: [],
    ...draft,
  };
}

/** A task with its thread: its counts and what it waits on are read from the thread, as the server does. */
function thread(
  draft: Pick<TaskThread, "id" | "title" | "executor" | "owner" | "origin"> & {
    archived?: boolean;
    thread: TaskTurn[];
    notes?: string[];
  },
): TaskThread {
  const { archived = false, notes = [], ...rest } = draft;
  const first = rest.thread[0];
  if (!first) throw new Error("a task has at least one turn");
  return reread(
    {
      ...rest,
      notes,
      steers: true, // Hermes, Codex and Claude Code all take an instruction into the turn that works
      state: archived ? "archived" : "ready",
      created_at: first.started_at,
      last_activity: first.started_at,
      turns: 0,
      last_status: first.status,
      question: null,
      now: null,
    },
    archived,
  );
}

/** A task's state, counts and what it waits on, read again from its thread after a change; `archived` keeps it
 * put away unless a turn works. */
export function reread(task: TaskThread, archived = task.state === "archived"): TaskThread {
  const last = task.thread.at(-1);
  task.state =
    last?.status === "running" ? "working" : archived ? "archived" : last?.status === "asked" ? "waiting" : "ready";
  task.turns = task.thread.length;
  if (last) task.last_status = last.status;
  task.last_activity = last ? (last.ended_at ?? last.started_at) : task.created_at;
  task.question = last?.status === "asked" ? last.question : null;
  task.now = last?.status === "running" ? (last.steps.at(-1) ?? null) : null;
  return task;
}

export function tasks(): TaskThread[] {
  return [
    thread({
      id: "t-4410aa",
      title: CLAIM_TITLE,
      executor: "hermes",
      owner: ref("mathis"),
      origin: { session: "s-mutuelle", channel: "telegram" },
      thread: [
        turn({
          id: "u-4410-1",
          instruction: CLAIM,
          by: ref("mathis"),
          status: "asked",
          started_at: minutes(30.9),
          ended_at: minutes(9),
          steps: CLAIM_STEPS,
          question: CLAIM_QUESTION,
          files: CLAIM_FILES,
          delivered: { at: minutes(8.8), channel: "telegram", room: null },
        }),
      ],
      notes: [CLAIM_NOTE],
    }),
    thread({
      id: "t-88b07e",
      title: SHOPPING_TITLE,
      executor: "codex",
      owner: ref("lea"),
      origin: { session: "s-courses", channel: "web" },
      thread: [
        turn({
          id: "u-88b0-1",
          instruction: SHOPPING,
          by: ref("lea"),
          status: "running",
          started_at: minutes(11.9),
          steps: [SHOPPING_STEP],
          steered: [{ instruction: SHOPPING_STEER, by: ref("lea"), at: minutes(5.5) }],
        }),
      ],
    }),
    thread({
      id: "t-3f2a1c",
      title: ENERGY_TITLE,
      executor: "hermes",
      owner: ref("mathis"),
      origin: { session: "s-elec", channel: "telegram" },
      thread: [
        turn({
          id: "u-3f2a-1",
          instruction: ENERGY,
          by: ref("mathis"),
          status: "completed",
          started_at: minutes(351.6),
          ended_at: minutes(251),
          steps: ENERGY_STEPS,
          result: ENERGY_RESULT,
          files: [...ENERGY_BILLS, ...ENERGY_FILES],
          delivered: { at: minutes(250.4), channel: "voice", room: OFFICE },
        }),
        turn({
          id: "u-3f2a-2",
          instruction: ENERGY_FOLLOW_UP,
          by: ref("mathis"),
          status: "completed",
          started_at: minutes(212),
          ended_at: minutes(196),
          steps: [ENERGY_OFF_PEAK_STEP],
          result: ENERGY_OFF_PEAK,
          files: ENERGY_OFF_PEAK_FILES,
          delivered: { at: minutes(195.8), channel: "telegram", room: null },
        }),
      ],
      notes: ENERGY_NOTES,
    }),
    thread({
      id: "t-c1a9de",
      title: DEPENDENCIES_TITLE,
      executor: "claude-code",
      owner: ref("mathis"),
      origin: { session: "s-slack", channel: "slack" },
      thread: [
        turn({
          id: "u-c1a9-1",
          instruction: DEPENDENCIES,
          by: ref("mathis"),
          status: "completed",
          started_at: minutes(539.5),
          ended_at: minutes(521),
          steps: [fr("Tests pass on the new versions.", "Les tests passent avec les nouvelles versions.")],
          result: DEPENDENCIES_RESULT,
          files: DEPENDENCIES_FILES,
          delivered: { at: minutes(520.8), channel: "slack", room: null },
        }),
      ],
    }),
    thread({
      id: "t-a04f12",
      title: fr("Gym membership cancellation", "Résiliation de la salle de sport"),
      executor: "hermes",
      owner: ref("lea"),
      origin: { session: "telegram:@lea_martin", channel: "telegram" },
      thread: [
        turn({
          id: "u-a04f-1",
          instruction: fr("Cancel the gym membership.", "Résilier l'abonnement à la salle de sport."),
          by: ref("lea"),
          status: "failed",
          started_at: minutes(60 * 26),
          ended_at: minutes(60 * 26 - 9),
          error: GYM_ERROR,
        }),
      ],
    }),
    thread({
      id: "t-5e6b70",
      title: fr("Jules's homework", "Devoirs de Jules"),
      executor: "codex",
      owner: ref("jules"),
      origin: { session: "voice:pi-bedroom", channel: "voice" },
      archived: true,
      thread: [
        turn({
          id: "u-5e6b-1",
          instruction: fr("Sum up Jules's homework for the week.", "Récapituler les devoirs de Jules pour la semaine."),
          by: ref("jules"),
          status: "stopped",
          started_at: minutes(60 * 30),
          ended_at: minutes(60 * 30 - 1),
        }),
      ],
    }),
  ];
}

/** The watch on the school's reply: its name and what it watches for, as its creation reads in the journal. */
export const SCHOOL_TRIP_WATCH = fr("School trip reply", "Réponse pour la sortie scolaire");
export const SCHOOL_TRIP = fr(
  "News from the school: tell Léa as soon as the school replies about the trip.",
  "Les nouvelles de l'école : prévenir Léa dès que l'école répond pour la sortie.",
);

export function watches(): Watch[] {
  return [
    {
      id: "w-9d41",
      title: SCHOOL_TRIP_WATCH,
      what: SCHOOL_TRIP,
      owner: ref("lea"),
      kinds: ["mail"],
      once: false,
      created_at: minutes(60 * 28),
      until: ahead(60 * 60 * 24 * 6),
      origin: { session: "s-hier", channel: "telegram" },
      triggered: 1,
      last_triggered_at: minutes(230),
    },
    {
      id: "w-2b77",
      title: fr("Jules's school", "École de Jules"),
      what: fr("Messages from Jules's school.", "Les messages de l'école de Jules."),
      owner: null,
      kinds: ["mail"],
      once: false,
      created_at: minutes(60 * 24 * 14),
      until: null,
      origin: null,
      triggered: 7,
      last_triggered_at: minutes(96),
    },
    {
      id: "w-f31a",
      title: fr("Python 3.15 on LWN", "Python 3.15 sur LWN"),
      what: fr("Tell me when LWN writes about Python 3.15.", "Préviens-moi quand LWN parle de Python 3.15."),
      owner: ref("mathis"),
      kinds: ["feed"],
      once: false,
      created_at: minutes(60 * 24 * 3),
      until: null,
      origin: { session: "s-slack", channel: "slack" },
      triggered: 1,
      last_triggered_at: minutes(458),
    },
    {
      id: "w-p8c2",
      title: fr("Summer camp sign-ups", "Inscriptions au centre aéré"),
      what: fr(
        "Tell me when the town hall opens the summer camp sign-ups.",
        "Préviens-moi quand la mairie ouvre les inscriptions au centre aéré.",
      ),
      owner: ref("lea"),
      kinds: ["page"],
      once: true,
      created_at: minutes(60 * 24 * 6),
      until: ahead(60 * 60 * 24 * 30),
      origin: { session: "s-signal", channel: "signal" },
      triggered: 0,
      last_triggered_at: null,
    },
    {
      id: "w-h5e0",
      title: fr("Washing machine done", "Machine à laver finie"),
      what: fr(
        "Tell whoever is home when the washing machine is done.",
        "Dire à qui est là quand la machine est finie.",
      ),
      owner: null,
      kinds: ["washing-machine"],
      once: false,
      created_at: minutes(60 * 24 * 20),
      until: null,
      origin: null,
      triggered: 23,
      last_triggered_at: minutes(427),
    },
  ];
}

/** Reminders: one for tomorrow morning, three that come back. */
export function schedules(): Schedule[] {
  return [
    {
      id: "sc-bread",
      title: fr("Buy bread", "Acheter du pain"),
      instruction: fr("Remind Mathis to buy bread.", "Rappeler à Mathis d'acheter du pain."),
      owner: ref("mathis"),
      origin: { session: "telegram:@mathis_l", channel: "telegram" },
      recurring: false,
      once_at: ahead(60 * 60 * 9),
      times: [],
      days: [],
      next_due: ahead(60 * 60 * 9),
    },
    {
      id: "sc-tv",
      title: fr("Samsung TV price", "Prix de la télé Samsung"),
      instruction: fr(
        "Check the price of the Samsung 65S92H; tell Mathis only below €1,600.",
        "Vérifier le prix du Samsung 65S92H ; prévenir Mathis seulement sous 1 600 €.",
      ),
      owner: ref("mathis"),
      origin: { session: "telegram:@mathis_l", channel: "telegram" },
      recurring: true,
      once_at: null,
      times: ["10:00"],
      days: [],
      next_due: ahead(60 * 60 * 12),
    },
    {
      id: "sc-bins",
      title: fr("Bins out", "Sortir les poubelles"),
      instruction: fr("Remind Jules to take the bins out.", "Rappeler à Jules de sortir les poubelles."),
      owner: ref("lea"),
      origin: null,
      recurring: true,
      once_at: null,
      times: ["19:00"],
      days: ["tue"],
      next_due: ahead(60 * 60 * 24 * 4),
    },
    {
      id: "sc-plants",
      title: fr("Water the plants", "Arroser les plantes"),
      instruction: fr("Remind Léa to water the plants.", "Rappeler à Léa d'arroser les plantes."),
      owner: ref("lea"),
      origin: null,
      recurring: true,
      once_at: null,
      times: ["09:00"],
      days: ["sat", "sun"],
      next_due: ahead(60 * 60 * 30),
    },
  ];
}

/** A question to Léa waiting for her answer, and a message that has not found its way yet. */
export function messages(): Messages {
  return {
    questions: [
      {
        id: "msg-car",
        to: ref("lea"),
        text: fr("Do you need the car tomorrow?", "Tu as besoin de la voiture demain ?"),
        requested_by: ref("mathis"),
        expects_reply: true,
        channel: null,
        at: minutes(40),
      },
    ],
    pending: [
      {
        id: "msg-odile",
        to: ref("odile"),
        text: fr("Lunch is at noon on Sunday.", "Le déjeuner est à midi dimanche."),
        requested_by: ref("lea"),
        expects_reply: false,
        channel: "telegram",
        at: minutes(3),
      },
    ],
  };
}

/** Unlocking the front door, asked aloud in the hallway, waiting for Mathis. */
export function confirmations(): Confirmation[] {
  return [
    {
      id: "cf-door",
      person: ref("mathis"),
      tool: "intent__HassTurnOff",
      arguments: { name: fr("Front door", "Porte d'entrée"), domain: ["lock"] },
      origin: { session: `voice:${HALLWAY}`, channel: "voice" },
      expires_at: ahead(4 * 60),
      yours: true,
    },
  ];
}

/** What Home Assistant lets the agent do. */
function homeTools(): Home["tools"] {
  return [
    {
      name: "homeassistant__GetLiveContext",
      description: fr("The state of every exposed device.", "L'état de chaque appareil exposé."),
      risk: "read",
      confirmed_when: false,
    },
    {
      name: "intent__HassTurnOff",
      description: fr("Turns off a device or entity.", "Éteint un appareil ou une entité."),
      risk: "write",
      confirmed_when: true,
    },
    {
      name: "intent__HassTurnOn",
      description: fr("Turns on a device or entity.", "Allume un appareil ou une entité."),
      risk: "write",
      confirmed_when: true,
    },
    {
      name: "light__HassLightSet",
      description: fr("Sets the brightness or colour of a light.", "Règle la luminosité ou la couleur d'une lumière."),
      risk: "write",
      confirmed_when: true,
    },
  ];
}

/**
 * Home Assistant as the file plugs it in (`component`, of the system's): the people the file ties to its entities,
 * its rooms and who it sees in them, and the actions it offers. `null` when the file has no home.
 */
export function home(
  doc: ConfigDocument,
  component: Component | undefined,
  satellites: readonly Satellite[],
): Home | null {
  if (!component || !isRecord(doc.home)) return null;
  const entities = isRecord(doc.home.people) ? doc.home.people : {};
  const trackers = isRecord(doc.home.rooms) ? doc.home.rooms : {};
  const crowd = people(doc);
  const entity = (id: string) => (typeof entities[id] === "string" ? (entities[id] as string) : null);
  return {
    component: { ...component },
    connected: true,
    granularity: "person_room",
    rooms: ROOMS.map(([id, name, occupied]) => ({
      id,
      name,
      occupied,
      people: crowd.filter((p) => p.presence?.room === id).map((p) => ref(p.id)),
      satellites: satellites.filter((s) => s.room === id).map((s) => s.id),
    })),
    // what Home Assistant itself knows: its `person` entities, tied to someone of the file or not
    residents: [
      ...crowd.flatMap((p) => {
        const known = entity(p.id);
        return known ? [{ entity: known, name: p.name, home: p.presence?.home ?? null, person: ref(p.id) }] : [];
      }),
      { entity: "person.guest", name: fr("Guest", "Invité"), home: null, person: null },
    ],
    people: crowd.map((p) => ({
      person: ref(p.id),
      entity: entity(p.id),
      tracker: typeof trackers[p.id] === "string" ? (trackers[p.id] as string) : null,
      presence: entity(p.id) && p.presence ? p.presence : { home: null, room: null, since: null },
    })),
    unplaced_sensors: ["binary_sensor.garage_motion"],
    tools: homeTools(),
  };
}

/** What Jules teaches Richie during the day. */
export const HANDBALL = fr(
  "Jules has handball practice on Wednesdays at 3 pm.",
  "Jules a entraînement de handball le mercredi à 15 h.",
);

/** Where m-07 was learnt: replaced by the journal position of the turn that taught it (db.ts). */
export const LEARNT = -1;

/** A place as the server sends it, from its path: `people/jules`, `home`, `projects/roof-works`. */
export function place(path: string): Place {
  const [shelf = "", name = null] = path.split("/") as [string, string?];
  if (!oneOf(shelfValues, shelf)) throw new Error(`no shelf ${shelf}`);
  return { path, shelf, name, person: shelf === "people" && name ? ref(name) : null };
}

/** The roof works and the garden, named by the agent: their French beside them, as a French household's would be. */
const ROOF = fr("projects/roof-works", "projects/travaux-toiture");
fr("roof-works", "travaux-toiture");
const GARDEN = fr("topics/garden", "topics/jardin");
fr("garden", "jardin");

export function memories(): Memory[] {
  const m = (
    id: string,
    text: string,
    where: string,
    told_by: string | null,
    learnt_in: string | null,
    ago: number,
    {
      learnt_event = null,
      session = null,
      tied_to = null,
    }: Partial<Pick<Memory, "learnt_event" | "session" | "tied_to">> = {},
  ): Memory => {
    const filed = place(where);
    return {
      id,
      text,
      place: filed,
      told_by: told_by ? ref(told_by) : null,
      tied_to,
      learnt_in,
      created_at: minutes(ago),
      updated_at: minutes(ago),
      learnt_event,
      session,
      editable: true,
    };
  };
  return [
    m(
      "m-01",
      fr("Jules is allergic to peanuts.", "Jules est allergique aux arachides."),
      "people/jules",
      "lea",
      "voice",
      60 * 24 * 18,
    ),
    m(
      "m-02",
      fr(
        "Mathis would rather not be spoken to before 8 am, unless it is urgent.",
        "Mathis préfère qu'on ne lui parle pas avant 8 h, sauf urgence.",
      ),
      "people/mathis",
      "mathis",
      "telegram",
      60 * 24 * 7,
    ),
    m(
      "m-03",
      fr(
        "The gate code is only ever given out loud, never in writing.",
        "Le code du portail est donné de vive voix uniquement, jamais par écrit.",
      ),
      "home",
      "mathis",
      "voice",
      60 * 24 * 30,
    ),
    m(
      "m-04",
      fr(
        "Odile comes for lunch on the first Sunday of every month.",
        "Odile vient déjeuner le premier dimanche de chaque mois.",
      ),
      "people/odile",
      "lea",
      "voice",
      60 * 30,
    ),
    m(
      "m-05",
      fr("Léa does yoga on Tuesday evenings, from 7 to 8:30 pm.", "Léa fait du yoga le mardi soir, de 19 h à 20 h 30."),
      "people/lea",
      "lea",
      "telegram",
      60 * 24 * 4,
    ),
    m(
      "m-06",
      fr("The boiler is serviced every year in October.", "La chaudière est révisée chaque année en octobre."),
      "home",
      "mathis",
      "voice",
      60 * 24 * 60,
    ),
    m("m-07", HANDBALL, "people/jules", "jules", "voice", 149.4, { learnt_event: LEARNT, session: "s-jules" }),
    m(
      "m-08",
      fr("The roofer comes back on Thursday to finish the north side.", "Le couvreur revient jeudi finir le pan nord."),
      ROOF,
      "mathis",
      "telegram",
      60 * 24 * 2,
    ),
    m(
      "m-09",
      fr("The roof quote is 8,400 €, gutters included.", "Le devis du toit est de 8 400 €, gouttières comprises."),
      ROOF,
      "mathis",
      "telegram",
      60 * 24 * 9,
    ),
    m(
      "m-10",
      fr(
        "The tomatoes go in after the last frost, around mid-May.",
        "Les tomates se plantent après les dernières gelées, vers la mi-mai.",
      ),
      GARDEN,
      "lea",
      "voice",
      60 * 24 * 40,
    ),
    m(
      "m-11",
      fr("Sunday mornings are for the market, all together.", "Le dimanche matin, c'est marché, tous ensemble."),
      "household",
      "lea",
      "voice",
      60 * 24 * 21,
    ),
    m(
      "m-12",
      fr(
        "Léa wants oat milk, not soy, in this week's shopping.",
        "Léa veut du lait d'avoine, pas de soja, dans les courses de la semaine.",
      ),
      "people/lea",
      "lea",
      "web",
      11.5,
      { session: "s-courses", tied_to: "task:t-88b07e" },
    ),
  ];
}

/**
 * What the nightly upkeep merged and set aside, and the memory that went when its task ended, newest first; their
 * journal positions are the day's (db.ts).
 */
export function retired(): Retired[] {
  const r = (
    memory_id: string,
    text: string,
    where: string,
    reason: Retirement,
    ago: number,
    {
      why = null,
      tied_to = null,
      into = null,
      merged_text = null,
    }: Partial<Pick<Retired, "why" | "tied_to" | "into" | "merged_text">> = {},
  ): Retired => ({
    memory_id,
    text,
    place: place(where),
    reason,
    why,
    tied_to,
    into,
    merged_text,
    at: minutes(ago),
    event: 0,
  });
  return [
    r(
      "m-r3",
      fr(
        "Mathis wants the dependency update to keep Node 22.",
        "Mathis veut que la mise à jour des dépendances garde Node 22.",
      ),
      "people/mathis",
      "ended",
      520.7,
      { tied_to: "task:t-c1a9de" },
    ),
    r(
      "m-r2",
      fr("The boiler's next service is on 14 October.", "La prochaine révision de la chaudière est le 14 octobre."),
      "home",
      "stale",
      529.8,
      {
        why: fr(
          "That service is past; the yearly one in October stays.",
          "Cette révision est passée ; celle de chaque mois d'octobre reste.",
        ),
      },
    ),
    r(
      "m-r1",
      fr("Jules has handball on Wednesday afternoons.", "Jules a handball le mercredi après-midi."),
      "people/jules",
      "merged",
      529.9,
      { into: "m-07", merged_text: HANDBALL },
    ),
  ];
}

/** What the release feed says: two releases after the running 0.9.0, the newest one breaking. */
export function updates(): Updates {
  return {
    running: "0.9.0",
    releases: [
      {
        version: "0.10.0",
        date: "2026-11-04",
        url: "https://github.com/nestor-home/nestor/releases/tag/v0.10.0",
        breaking: true,
        changes: [
          { kind: "breaking", text: "the satellite manifest names its software" },
          { kind: "feature", text: "satellites update themselves from the admin" },
          { kind: "feature", text: "the admin says when a newer Nestor is out" },
          { kind: "fix", text: "a typed follow-up stays in the room's conversation" },
        ],
      },
      {
        version: "0.9.1",
        date: "2026-11-03",
        url: "https://github.com/nestor-home/nestor/releases/tag/v0.9.1",
        breaking: false,
        changes: [{ kind: "fix", text: "serve a channel again after it stops" }],
      },
    ],
    left_behind: [],
    installation: "pip",
    commands: ["pip install --upgrade 'nestor-home[voice]'"],
    installable: true,
    installing: null,
    failed: null,
  };
}

/** What only a running component tells, by `slot/name`: its health when not well, its version, who it is there. */
type Observed = Partial<Pick<Component, "version" | "health" | "health_detail" | "capabilities">>;
const OBSERVED: Record<string, Observed> = {
  "model/sonnet": {
    health_detail: fr("First token in 640 ms (today's median)", "Premier jeton en 640 ms (médiane du jour)"),
    capabilities: ["tools", "streaming"],
  },
  "executor/hermes": { version: "0.6.1" },
  "executor/codex": { version: "0.48" },
  "executor/claude-code": { version: "2.1.4" },
  "channel/satellites": { version: PROTOCOL },
  "channel/telegram": { version: "Bot API 9.2", health_detail: "@richie_martin_bot" },
  "channel/discord": { health_detail: "Richie#4012" },
  "channel/slack": { health_detail: "martin-family.slack.com" },
  "channel/matrix": { health_detail: "@richie:matrix.martin.family" },
  "channel/whatsapp": { health_detail: "+33 6 55 50 42 18" },
  "channel/openai-api": { health_detail: "/v1/chat/completions" },
  "home/home": { version: "2026.10.2" },
  "tools/recipes": { health: "unavailable" },
};

/** What the rest of the instance does to a component's health: accounts, satellites, tasks. */
export interface Running {
  satellites: readonly Satellite[];
  connections: readonly Connection[];
  tasks: readonly TaskThread[];
}

const hostOf = (url: unknown) => (typeof url === "string" && URL.canParse(url) ? new URL(url).host : String(url));
const count = (value: unknown) => (Array.isArray(value) ? value.length : 0);

/** What a component says of itself from its settings and from what goes through it; `null`: nothing to say. */
function told(p: Plugged, health: Component["health"], running: Running): string | null {
  const { entry } = p;
  if (p.slot === "executor") {
    const busy = running.tasks.filter((t) => t.executor === p.name && t.state === "working").length;
    if (!busy) return null;
    return busy === 1
      ? fr("1 task running", "1 tâche en cours")
      : fr(`${busy} tasks running`, `${busy} tâches en cours`);
  }
  if (p.slot === "channel") {
    if (p.plugin === "satellites") {
      const all = running.satellites.length;
      const connected = running.satellites.filter((s) => s.connected).length;
      return fr(`${connected} of ${all} satellites connected`, `${connected} satellites connectés sur ${all}`);
    }
    if (p.plugin === "email") return String(entry.address);
    if (p.plugin === "signal") return String(entry.number);
    if (p.plugin === "ntfy" || p.plugin === "webhook") return hostOf(entry.url);
    return null;
  }
  if (p.slot === "inbound") {
    const n = count(entry.feeds) || count(entry.pages) || count(entry.hooks);
    if (p.plugin === "rss")
      return n === 1 ? fr("1 feed followed", "1 flux suivi") : fr(`${n} feeds followed`, `${n} flux suivis`);
    if (p.plugin === "web-page")
      return n === 1 ? fr("1 page followed", "1 page suivie") : fr(`${n} pages followed`, `${n} pages suivies`);
    return n === 1 ? "1 webhook" : `${n} webhooks`;
  }
  if (p.slot === "home") {
    const tied = isRecord(entry.people) ? Object.keys(entry.people).length : 0;
    const actions = homeTools().length;
    return fr(`${tied} people tied, ${actions} actions`, `${tied} personnes reliées, ${actions} actions`);
  }
  if (p.slot === "tools" && health === "unavailable") {
    const host = hostOf(entry.url);
    return fr(`Connection refused by ${host}`, `Connexion refusée par ${host}`);
  }
  return null;
}

/** A connector is as well as its accounts: one to authorise again and it is degraded. */
function reauthorise(p: Plugged, running: Running): Observed {
  const stale = running.connections.filter((c) => c.kind === p.plugin && c.status === "needs_reauth").length;
  if (!stale) return {};
  return {
    health: "degraded",
    health_detail:
      stale === 1
        ? fr("1 account to authorise again", "1 compte à réautoriser")
        : fr(`${stale} accounts to authorise again`, `${stale} comptes à réautoriser`),
  };
}

/**
 * What is plugged in: every component of the configuration file Nestor started on, named and branded as the file
 * says, with what it tells once running; then the paired satellites, as the server presents them.
 */
export function components(doc: ConfigDocument, running: Running): Component[] {
  const configured = plugged(doc).map((p): Component => {
    const observed = { ...OBSERVED[`${p.slot}/${p.name}`], ...(p.slot === "connector" ? reauthorise(p, running) : {}) };
    const health = observed.health ?? "started";
    return {
      slot: p.slot,
      name: p.name,
      adapter: p.plugin,
      model_type: p.model_type,
      fallback: p.fallback,
      brand: p.brand,
      version: observed.version ?? (p.slot === "model" && typeof p.entry.model === "string" ? p.entry.model : null),
      distribution: null,
      capabilities: observed.capabilities ?? [],
      health,
      health_detail: observed.health_detail ?? told(p, health, running),
      details: {},
      docs: (pluginDocs as Record<string, string>)[`${p.slot}/${p.plugin}`] ?? null,
    };
  });
  const paired = running.satellites.map((s): Component => {
    const offline = Math.round((Date.now() - Date.parse(s.last_seen_at ?? "")) / 60_000);
    return {
      slot: "satellite",
      name: s.id,
      adapter: s.model,
      model_type: null,
      fallback: null,
      brand: s.brand,
      version: s.software.version,
      distribution: s.software.name,
      capabilities: s.capabilities.map((c) => c.name).sort(),
      health: s.connected ? "started" : "unavailable",
      health_detail: s.connected ? s.room : fr(`Offline for ${offline} min`, `Hors ligne depuis ${offline} min`),
      details: { room: s.room },
      docs: null,
    };
  });
  return [...configured, ...paired];
}

export function system(doc: ConfigDocument, running: Running): SystemInfo {
  return {
    nestor: { version: updates().running },
    agent: { name: ASSISTANT, status: "started" },
    restart_required: false,
    pending_changes: [],
    components: components(doc, running),
  };
}

/** The keys Nestor's MCP server knows the executors by: Claude Code has had no task through it yet, so no key. */
const KEYS: Record<string, Executors["executors"][number]["key"]> = {
  hermes: { issued_at: minutes(60 * 24 * 3), last_used_at: minutes(42) },
  codex: { issued_at: minutes(60 * 24 * 6), last_used_at: minutes(60 * 5) },
};

/**
 * The executors of the file and their keys for Nestor's MCP server, served at the admin's public address: Hermes
 * declares it in its own profile when the file says so, Nestor hands it to the others with each task.
 */
export function executors(doc: ConfigDocument): Executors {
  const address = publicUrl(doc);
  return {
    url: address ? `${address}/mcp` : null,
    executors: plugged(doc)
      .filter((p) => p.slot === "executor")
      .map((p) => ({
        name: p.name,
        description: String(p.entry.description ?? ""),
        nestor_tools: p.plugin === "hermes" ? (p.entry.nestor_mcp ? "configured" : "none") : "passed",
        key: KEYS[p.name] ?? null,
      })),
  };
}
