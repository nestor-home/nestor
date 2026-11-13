/**
 * A believable household for development and tests: Richie serving the Lambert family. Written in
 * English, with the French of each text beside it (`fr`) for an admin read in French.
 */
import type {
  Account,
  Capability,
  Component,
  Confirmation,
  Connection,
  Connector,
  Home,
  Invitation,
  Memory,
  Messages,
  PairingMethod,
  PairingMethodId,
  PairingRequest,
  Person,
  PersonRef,
  Role,
  Satellite,
  Schedule,
  Scope,
  Service,
  SystemInfo,
  Task,
  Tool,
  Updates,
  Voice,
  Watch,
} from "@/api";
import { scopeValues } from "@/api/schema.gen";
import { oneOf } from "@/lib/enums";
import { fr } from "./french";
import grants from "./server/role-scopes.json";

export const ASSISTANT = "Richie";

const NAMES: Record<string, string> = { mathis: "Mathis", lea: "Léa", jules: "Jules", odile: "Odile" };

/** A person as the API names them everywhere: `{id, name}`. */
export const ref = (id: string): PersonRef => ({ id, name: NAMES[id] ?? id });

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

export function people(): MockPerson[] {
  return [
    {
      id: "mathis",
      name: "Mathis",
      channel_accounts: ["voice", "telegram:@mathis_l"],
      reach: "telegram:@mathis_l",
      presence: { home: true, room: LIVING_ROOM, since: minutes(61) },
      account: "acc-mathis",
    },
    {
      id: "lea",
      name: "Léa",
      channel_accounts: ["voice", "telegram:@lea_lambert", "web"],
      reach: "voice",
      presence: { home: false, room: null, since: minutes(205) },
      account: "acc-lea",
    },
    {
      id: "jules",
      name: "Jules",
      channel_accounts: ["voice"],
      reach: "voice",
      presence: { home: true, room: LIVING_ROOM, since: minutes(2) },
      account: null,
    },
    {
      id: "odile",
      name: "Odile",
      channel_accounts: ["telegram:@odile.m"],
      reach: "telegram:@odile.m",
      presence: { home: null, room: null, since: null },
      account: null,
    },
  ];
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

/** The guide shown before connecting a Google service. */
const googleSetup = (api: string) =>
  fr(
    `1. Open the Google Cloud console and create a project for the household.
2. Enable the ${api} API (APIs & Services › Library).
3. Under “OAuth consent screen”, choose “External” and add your addresses as test users.
4. Create “OAuth client ID” credentials, type “Web application”.
5. Declare the redirect URI below, then copy the client ID and secret.`,
    `1. Ouvrez la console Google Cloud et créez un projet pour le foyer.
2. Activez l'API ${api} (API et services › Bibliothèque).
3. Dans « Écran de consentement OAuth », choisissez « Externe » et ajoutez vos adresses comme utilisateurs test.
4. Créez des identifiants « ID client OAuth », type « Application Web ».
5. Déclarez l'URI de redirection ci-dessous, puis copiez l'identifiant et le secret.`,
  );
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

export function connectors(): Connector[] {
  return [
    {
      kind: "google",
      brand: "gmail",
      title: "Gmail",
      description: fr(
        "Read, search and draft emails; watch what arrives in the inbox.",
        "Lire, chercher et rédiger des courriels ; surveiller ce qui arrive dans la boîte.",
      ),
      auth: "oauth2",
      inbound: ["mail"],
      setup: googleSetup("Gmail"),
      fields: [],
      presets: [],
      oauth: {
        registered: true,
        client_id: "418230-9kq3hc.apps.googleusercontent.com",
        redirect_uri: "https://relay.nestor.dev/oauth/callback",
        relayed: true,
      },
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
        redirect_uri: "https://relay.nestor.dev/oauth/callback",
        relayed: true,
      },
    },
    {
      kind: "google-calendar",
      brand: "google-calendar",
      title: "Google Calendar",
      description: fr(
        "Read the household's calendars and add events.",
        "Consulter les agendas du foyer et y ajouter des événements.",
      ),
      auth: "oauth2",
      inbound: [],
      setup: googleSetup("Google Calendar"),
      fields: [],
      presets: [],
      oauth: {
        registered: false,
        client_id: null,
        redirect_uri: "https://relay.nestor.dev/oauth/callback",
        relayed: true,
      },
    },
  ];
}

/** Why a connection needs a look, as the server words it: a message and its text. */
const reason = (text: string) => ({ message: { id: "connection-status-reason", args: {} }, text });

export function connections(): Connection[] {
  return [
    {
      id: "c-gmail-mathis",
      kind: "google",
      brand: "gmail",
      title: "Gmail",
      account: "mathis.lambert27@gmail.com",
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
      account: "lea@lambert.family",
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
  ];
}

/** What each account gives access to, as a message names it (`handle` null while it is not connected). */
export function services(connection: Connection): Service[] {
  const named = (name: string, brand: string | null): Service => ({
    name,
    brand,
    handle: connection.status === "connected" ? name : null,
  });
  if (connection.kind === "google") {
    return [
      named("gmail", "gmail"),
      named("calendar", "google-calendar"),
      named("drive", "google-drive"),
      named("contacts", "google"),
      named("tasks", "google-tasks"),
    ];
  }
  if (connection.kind === "imap") return [named("mail", "imap")];
  return [named(connection.id === "c-mcp-ha" ? "homeassistant" : "recipes", connection.brand)];
}

export function tools(kind: string): Tool[] {
  if (kind === "google" || kind === "imap") {
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

export function satellites(): Satellite[] {
  return [
    {
      id: "reachy-living-room",
      name: fr("Living room Reachy", "Reachy du salon"),
      can_identify: true,
      model: "Reachy Mini",
      room: LIVING_ROOM,
      capabilities: [MIC, SPEAKER, VAD, PEOPLE, FACE, HEAD, UPDATE],
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
    },
    {
      id: "reachy-office",
      name: null,
      can_identify: true,
      model: "Reachy Mini",
      room: OFFICE,
      capabilities: [MIC, SPEAKER, VAD, FACE],
      paired_at: minutes(60 * 24 * 20),
      approved_by: ref("mathis"),
      connected: false,
      last_seen_at: minutes(97),
      brand: "reachy",
      software: { name: "nestor-reachy", version: "0.4.0" },
      protocol: PROTOCOL,
      can_update: false,
      update: null,
    },
    {
      id: "pi-bedroom",
      name: fr("Jules's speaker", "Enceinte de Jules"),
      can_identify: false,
      model: "Raspberry Pi 5 · ReSpeaker",
      room: BEDROOM,
      capabilities: [MIC, SPEAKER],
      paired_at: minutes(60 * 24 * 12),
      approved_by: ref("lea"),
      connected: true,
      last_seen_at: minutes(0.5),
      brand: "raspberry-pi",
      software: { name: "nestor-satellite", version: "0.5.1" },
      protocol: PROTOCOL,
      can_update: true,
      update: { state: "current", version: null, notes: null },
    },
  ];
}

/** What the tasks are about, also written in the journal. */
export const CLAIM = fr(
  "Prepare the health insurance claim for Jules's glasses.",
  "Préparer le dossier de remboursement de la mutuelle pour les lunettes de Jules.",
);
export const CLAIM_STEPS = [
  fr("Insurance claim form downloaded.", "Formulaire de la mutuelle téléchargé."),
  fr("Waiting for the invoice: Gmail needs reconnecting.", "En attente de la facture : Gmail est à reconnecter."),
];
export const SHOPPING = fr(
  "Make the week's shopping list from Léa's menus.",
  "Préparer la liste de courses de la semaine à partir des menus de Léa.",
);
export const SHOPPING_STEP = fr(
  "Reading the “Léa's recipes” MCP server.",
  "Lecture du serveur MCP « Recettes de Léa ».",
);
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
export const GYM_ERROR = fr(
  "The site asks for a sign-in by text message: impossible without Léa.",
  "Le site demande une connexion par SMS : impossible sans Léa.",
);

export function tasks(): Task[] {
  return [
    {
      id: "t-4410aa",
      objective: CLAIM,
      executor: "hermes",
      status: "running",
      requested_by: ref("mathis"),
      started_at: minutes(30.9),
      ended_at: null,
      steps: CLAIM_STEPS,
      result: null,
      error: null,
      origin: { session: "s-mutuelle", channel: "telegram" },
      delivered: null,
      files: [],
    },
    {
      id: "t-88b07e",
      objective: SHOPPING,
      executor: "codex",
      status: "running",
      requested_by: ref("lea"),
      started_at: minutes(11.9),
      ended_at: null,
      steps: [SHOPPING_STEP],
      result: null,
      error: null,
      origin: { session: "s-courses", channel: "web" },
      delivered: null,
      files: [],
    },
    {
      id: "t-3f2a1c",
      objective: ENERGY,
      executor: "hermes",
      status: "completed",
      requested_by: ref("mathis"),
      started_at: minutes(351.6),
      ended_at: minutes(251),
      steps: ENERGY_STEPS,
      result: ENERGY_RESULT,
      error: null,
      origin: { session: "s-elec", channel: "telegram" },
      delivered: { at: minutes(250.4), channel: "voice", room: OFFICE },
      files: [],
    },
    {
      id: "t-a04f12",
      objective: fr("Cancel the gym membership.", "Résilier l'abonnement à la salle de sport."),
      executor: "hermes",
      status: "failed",
      requested_by: ref("lea"),
      started_at: minutes(60 * 26),
      ended_at: minutes(60 * 26 - 9),
      steps: [],
      result: null,
      error: GYM_ERROR,
      origin: { session: "telegram:@lea_lambert", channel: "telegram" },
      delivered: null,
      files: [],
    },
    {
      id: "t-5e6b70",
      objective: fr("Sum up Jules's homework for the week.", "Récapituler les devoirs de Jules pour la semaine."),
      executor: "codex",
      status: "cancelled",
      requested_by: ref("jules"),
      started_at: minutes(60 * 30),
      ended_at: minutes(60 * 30 - 1),
      steps: [],
      result: null,
      error: null,
      origin: { session: "voice:pi-bedroom", channel: "voice" },
      delivered: null,
      files: [],
    },
  ];
}

/** A task's label once cancelled (the admin can cancel one). */

export function watches(): Watch[] {
  return [
    {
      id: "w-9d41",
      what: fr(
        "News from the school: tell Léa as soon as the school replies about the trip.",
        "Les nouvelles de l'école : prévenir Léa dès que l'école répond pour la sortie.",
      ),
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
  ];
}

/** Wake-ups and reminders: one for tomorrow morning, two that come back. */
export function schedules(): Schedule[] {
  return [
    {
      id: "sc-bread",
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
      id: "sc-plants",
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

/** Home Assistant: who it knows, its rooms and the actions it offers. */
export function home(): Home {
  const tied = (id: string, entity: string | null, presence: Person["presence"]) => ({
    person: ref(id),
    entity,
    tracker: entity ? `sensor.${id}_area` : null,
    presence: presence ?? { home: null, room: null, since: null },
  });
  const crowd = people();
  const of = (id: string) => crowd.find((p) => p.id === id)?.presence ?? null;
  return {
    component: component({
      slot: "home",
      name: "home",
      adapter: "home-assistant",
      brand: "homeassistant",
      version: "2026.10.2",
      health: "started",
      health_detail: null,
    }),
    connected: true,
    granularity: "person_room",
    rooms: [
      {
        id: LIVING_ROOM,
        name: fr("Living room", "Salon"),
        occupied: true,
        people: [ref("mathis"), ref("jules")],
        satellites: ["reachy-living-room"],
      },
      { id: KITCHEN, name: fr("Kitchen", "Cuisine"), occupied: false, people: [], satellites: [] },
      { id: OFFICE, name: fr("Office", "Bureau"), occupied: null, people: [], satellites: ["reachy-office"] },
      { id: HALLWAY, name: fr("Hallway", "Entrée"), occupied: false, people: [], satellites: [] },
      { id: BEDROOM, name: fr("Bedroom", "Chambre"), occupied: false, people: [], satellites: ["pi-bedroom"] },
    ],
    residents: [
      { entity: "person.mathis", name: "Mathis", home: true, person: ref("mathis") },
      { entity: "person.lea", name: "Léa", home: false, person: ref("lea") },
      { entity: "person.jules", name: "Jules", home: true, person: ref("jules") },
      { entity: "person.guest", name: fr("Guest", "Invité"), home: null, person: null },
    ],
    people: [
      tied("mathis", "person.mathis", of("mathis")),
      tied("lea", "person.lea", of("lea")),
      tied("jules", "person.jules", of("jules")),
      tied("odile", null, null),
    ],
    unplaced_sensors: ["binary_sensor.garage_motion"],
    tools: [
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
        description: fr(
          "Sets the brightness or colour of a light.",
          "Règle la luminosité ou la couleur d'une lumière.",
        ),
        risk: "write",
        confirmed_when: true,
      },
    ],
  };
}

/** What Jules teaches Richie during the day. */
export const HANDBALL = fr(
  "Jules has handball practice on Wednesdays at 3 pm.",
  "Jules a entraînement de handball le mercredi à 15 h.",
);

/** Where m-07 was learnt: replaced by the journal position of the turn that taught it (db.ts). */
export const LEARNT = -1;

export function memories(): Memory[] {
  const m = (
    id: string,
    text: string,
    about: string | null,
    told_by: string | null,
    learnt_in: string | null,
    ago: number,
    learnt_event: number | null = null,
    session: string | null = null,
  ): Memory => ({
    id,
    text,
    about: about ? ref(about) : null,
    told_by: told_by ? ref(told_by) : null,
    learnt_in,
    created_at: minutes(ago),
    updated_at: minutes(ago),
    learnt_event,
    session,
    editable: true,
  });
  return [
    m(
      "m-01",
      fr("Jules is allergic to peanuts.", "Jules est allergique aux arachides."),
      "jules",
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
      "mathis",
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
      null,
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
      "odile",
      "lea",
      "voice",
      60 * 30,
    ),
    m(
      "m-05",
      fr("Léa does yoga on Tuesday evenings, from 7 to 8:30 pm.", "Léa fait du yoga le mardi soir, de 19 h à 20 h 30."),
      "lea",
      "lea",
      "telegram",
      60 * 24 * 4,
    ),
    m(
      "m-06",
      fr("The boiler is serviced every year in October.", "La chaudière est révisée chaque année en octobre."),
      null,
      "mathis",
      "voice",
      60 * 24 * 60,
    ),
    m("m-07", HANDBALL, "jules", "jules", "voice", 149.4, LEARNT, "s-jules"),
  ];
}

const component = (
  c: Omit<Component, "capabilities" | "distribution" | "details" | "model_type" | "fallback"> &
    Partial<Pick<Component, "capabilities" | "model_type" | "fallback">>,
): Component => ({
  capabilities: [],
  distribution: null,
  details: {},
  model_type: null,
  fallback: null,
  ...c,
});

const ONE_TASK = fr("1 task running", "1 tâche en cours");
const PYTHON_SDK_042 = fr("Python SDK 0.4.2", "SDK Python 0.4.2");

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

export function system(): SystemInfo {
  return {
    nestor: { version: "0.10.0" },
    agent: { name: ASSISTANT, status: "started" },
    restart_required: false,
    pending_changes: [],
    components: [
      component({
        slot: "model",
        name: "sonnet",
        adapter: "openai-compatible-language",
        model_type: "language",
        brand: "openrouter",
        version: "anthropic/claude-sonnet-4.6",
        health: "started",
        health_detail: fr("First token in 640 ms (today's median)", "Premier jeton en 640 ms (médiane du jour)"),
        capabilities: ["tools", "streaming"],
      }),
      component({
        slot: "model",
        name: "haiku",
        adapter: "openai-compatible-language",
        model_type: "language",
        brand: "anthropic",
        version: "anthropic/claude-haiku-4.5",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "model",
        name: "scribe",
        adapter: "elevenlabs-transcription",
        model_type: "transcription",
        brand: "elevenlabs",
        version: "scribe_v2_realtime",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "model",
        name: "victor",
        adapter: "elevenlabs-speech",
        model_type: "speech",
        brand: "elevenlabs",
        version: "eleven_v4_turbo",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "executor",
        name: "Hermes",
        adapter: "hermes",
        brand: "hermes",
        version: "0.6.1",
        health: "started",
        health_detail: ONE_TASK,
      }),
      component({
        slot: "executor",
        name: "Codex",
        adapter: "codex",
        brand: "codex",
        version: "0.48",
        health: "started",
        health_detail: ONE_TASK,
      }),
      component({
        slot: "channel",
        name: fr("Voice (satellites)", "Voix (satellites)"),
        adapter: "satellites",
        brand: "voice",
        version: PROTOCOL,
        health: "started",
        health_detail: fr("2 of 3 satellites connected", "2 satellites connectés sur 3"),
      }),
      component({
        slot: "channel",
        name: "Telegram",
        adapter: "telegram",
        brand: "telegram",
        version: "Bot API 9.2",
        health: "started",
        health_detail: "@richie_lambert_bot",
      }),
      component({
        slot: "home",
        name: "home",
        adapter: "home-assistant",
        brand: "homeassistant",
        version: "2026.10.2",
        health: "started",
        health_detail: fr("4 people tied, 4 actions", "4 personnes reliées, 4 actions"),
      }),
      component({
        slot: "tools",
        name: fr("Léa's recipes (MCP)", "Recettes de Léa (MCP)"),
        adapter: "mcp",
        brand: "mcp",
        version: null,
        health: "unavailable",
        health_detail: fr("Connection refused by 192.168.1.20:8808", "Connexion refusée par 192.168.1.20:8808"),
      }),
      component({
        slot: "connector",
        name: "Gmail",
        adapter: "google",
        brand: "gmail",
        version: null,
        health: "degraded",
        health_detail: fr("1 account to authorise again", "1 compte à réautoriser"),
      }),
      component({
        slot: "connector",
        name: MAILBOX,
        adapter: "imap",
        brand: "imap",
        version: null,
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "satellite",
        name: "reachy-living-room",
        adapter: PYTHON_SDK_042,
        brand: "reachy",
        version: PROTOCOL,
        health: "started",
        health_detail: LIVING_ROOM,
      }),
      component({
        slot: "satellite",
        name: "reachy-office",
        adapter: fr("Python SDK 0.4.1", "SDK Python 0.4.1"),
        brand: "reachy",
        version: PROTOCOL,
        health: "unavailable",
        health_detail: fr("Offline for 97 min", "Hors ligne depuis 97 min"),
      }),
      component({
        slot: "satellite",
        name: "pi-bedroom",
        adapter: PYTHON_SDK_042,
        brand: "raspberry-pi",
        version: PROTOCOL,
        health: "started",
        health_detail: BEDROOM,
      }),
    ],
  };
}
