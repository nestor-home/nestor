/**
 * A believable household for development and tests: Richie serving the Lambert family. Written in
 * English, with the French of each text beside it (`fr`) for an admin read in French.
 */
import type {
  Account,
  Capability,
  Component,
  Connection,
  Connector,
  Invitation,
  Memory,
  PairingMethod,
  PairingMethodId,
  PairingRequest,
  Person,
  PersonRef,
  Role,
  Satellite,
  Scope,
  SystemInfo,
  Task,
  Tool,
  Updates,
  Voice,
  Watch,
} from "@/api";
import { fr } from "./french";

export const ASSISTANT = "Richie";

const NAMES: Record<string, string> = { mathis: "Mathis", lea: "Léa", jules: "Jules", odile: "Odile" };

/** A person as the API names them everywhere: `{id, name}`. */
export const ref = (id: string): PersonRef => ({ id, name: NAMES[id] ?? id });

export const minutes = (n: number, from = Date.now()) => new Date(from - n * 60_000).toISOString();
const ahead = (seconds: number) => new Date(Date.now() + seconds * 1000).toISOString();

/** The server's scopes for each role (what `/me` sends). */
const OWN: Scope[] = ["journal.read.own", "memory.manage.own"];
const MEMBER: Scope[] = [
  ...OWN,
  "household.read",
  "agent.read",
  "own.connections.manage",
  "tasks.manage.own",
  "watches.manage.own",
];
const ADMIN: Scope[] = [
  ...MEMBER,
  "accounts.manage",
  "household.connections.manage",
  "satellites.manage",
  "system.read",
  "config.manage",
  "journal.read.all",
  "memory.manage.all",
  "tasks.manage",
  "watches.manage.all",
];

/** Nestor's grants table (`permissions/grants.py`): owners hold every scope. */
export const SCOPES: Record<Role, Scope[]> = {
  owner: [...ADMIN, "accounts.owners.manage"],
  admin: ADMIN,
  member: MEMBER,
  guest: OWN,
};

export const ROLE_LABEL: Record<Role, string> = {
  owner: fr("owner", "propriétaire"),
  admin: fr("administrator", "administrateur"),
  member: fr("member", "membre"),
  guest: fr("guest", "invité"),
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
    role_label: ROLE_LABEL[role],
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
      role_label: ROLE_LABEL.member,
      person: ref("odile"),
      status: "pending",
      status_label: fr("pending", "en attente"),
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
const OAUTH = fr("OAuth", "OAuth");
const CREDENTIALS = fr("credentials", "identifiants");
const MAILBOX = fr("Mailbox (IMAP)", "Boîte mail (IMAP)");
const MCP_SERVER = fr("MCP server", "Serveur MCP");

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
      auth_label: OAUTH,
      inbound: ["mail"],
      setup: googleSetup("Gmail"),
      fields: [],
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
      auth_label: CREDENTIALS,
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
      oauth: null,
    },
    {
      kind: "mcp",
      brand: "mcp",
      title: MCP_SERVER,
      description: fr(
        "The tools of a Model Context Protocol server, local or remote: Home Assistant, your scripts…",
        "Les outils d'un serveur Model Context Protocol, local ou distant : Home Assistant, vos scripts…",
      ),
      auth: "secret",
      auth_label: CREDENTIALS,
      inbound: [],
      setup: fr(
        "Give the server's HTTP address (“streamable HTTP” transport). The token is optional.",
        "Indiquez l'adresse HTTP du serveur (transport « streamable HTTP »). Le jeton est facultatif.",
      ),
      fields: [
        {
          name: "name",
          label: fr("Display name", "Nom affiché"),
          secret: false,
          default: null,
        },
        {
          name: "url",
          label: fr("Server address", "Adresse du serveur"),
          secret: false,
          default: null,
        },
        { name: "token", label: fr("Access token", "Jeton d'accès"), secret: true, default: null },
      ],
      oauth: null,
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
      auth_label: OAUTH,
      inbound: [],
      setup: googleSetup("Google Calendar"),
      fields: [],
      oauth: {
        registered: false,
        client_id: null,
        redirect_uri: "https://relay.nestor.dev/oauth/callback",
        relayed: true,
      },
    },
  ];
}

const CONNECTED = fr("connected", "connectée");
/** Why a connection needs a look, as the server words it: a message and its text. */
const reason = (text: string) => ({ message: { id: "connection-status-reason", args: {} }, text });
/** Léa's MCP server of recipes. */
export const LEA_RECIPES = fr("Léa's recipes", "Recettes de Léa");

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
      status_label: fr("to authorise again", "à réautoriser"),
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
      status_label: CONNECTED,
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
      brand: "home-assistant",
      title: MCP_SERVER,
      account: fr("Home Assistant · home", "Home Assistant · maison"),
      owner: null,
      status: "connected",
      status_label: CONNECTED,
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
      account: LEA_RECIPES,
      owner: ref("lea"),
      status: "error",
      status_label: fr("error", "erreur"),
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

const READ = fr("read", "lecture");
const WRITE = fr("write", "écriture");
const SENSITIVE = fr("sensitive", "sensible");

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
        risk_label: READ,
        enabled: true,
      },
      {
        name: "mail_read",
        description: fr("Read an email and its text attachments.", "Lire un courriel et ses pièces jointes texte."),
        risk: "read",
        risk_label: READ,
        enabled: true,
      },
      {
        name: "mail_draft",
        description: fr("Draft a reply without sending it.", "Préparer un brouillon de réponse, sans l'envoyer."),
        risk: "write",
        risk_label: WRITE,
        enabled: true,
      },
      {
        name: "mail_label",
        description: fr("File an email (labels, archive).", "Classer un courriel (libellés, archivage)."),
        risk: "write",
        risk_label: WRITE,
        enabled: false,
      },
      {
        name: "mail_send",
        description: fr("Send an email on the person's behalf.", "Envoyer un courriel au nom de la personne."),
        risk: "sensitive",
        risk_label: SENSITIVE,
        enabled: false,
      },
    ];
  }
  return [
    {
      name: "ha_get_state",
      description: fr("Read the state of a device or sensor.", "Lire l'état d'un appareil ou d'un capteur."),
      risk: "read",
      risk_label: READ,
      enabled: true,
    },
    {
      name: "ha_list_areas",
      description: fr("List the rooms and their devices.", "Lister les pièces et leurs appareils."),
      risk: "read",
      risk_label: READ,
      enabled: true,
    },
    {
      name: "ha_turn_on",
      description: fr("Turn on a light, a plug or a scene.", "Allumer une lumière, une prise ou une scène."),
      risk: "write",
      risk_label: WRITE,
      enabled: true,
    },
    {
      name: "ha_turn_off",
      description: fr("Turn off a light, a plug or a scene.", "Éteindre une lumière, une prise ou une scène."),
      risk: "write",
      risk_label: WRITE,
      enabled: true,
    },
    {
      name: "ha_unlock",
      description: fr("Unlock a smart lock.", "Déverrouiller une serrure connectée."),
      risk: "sensitive",
      risk_label: SENSITIVE,
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

const RUNNING = fr("running", "en cours");

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
      status_label: RUNNING,
      requested_by: ref("mathis"),
      started_at: minutes(30.9),
      ended_at: null,
      steps: CLAIM_STEPS,
      result: null,
      error: null,
      origin: { session: "s-mutuelle", channel: "telegram" },
      delivered: null,
    },
    {
      id: "t-88b07e",
      objective: SHOPPING,
      executor: "codex",
      status: "running",
      status_label: RUNNING,
      requested_by: ref("lea"),
      started_at: minutes(11.9),
      ended_at: null,
      steps: [SHOPPING_STEP],
      result: null,
      error: null,
      origin: { session: "s-courses", channel: "web" },
      delivered: null,
    },
    {
      id: "t-3f2a1c",
      objective: ENERGY,
      executor: "hermes",
      status: "completed",
      status_label: fr("completed", "terminée"),
      requested_by: ref("mathis"),
      started_at: minutes(351.6),
      ended_at: minutes(251),
      steps: ENERGY_STEPS,
      result: ENERGY_RESULT,
      error: null,
      origin: { session: "s-elec", channel: "telegram" },
      delivered: { at: minutes(250.4), channel: "voice", room: OFFICE },
    },
    {
      id: "t-a04f12",
      objective: fr("Cancel the gym membership.", "Résilier l'abonnement à la salle de sport."),
      executor: "hermes",
      status: "failed",
      status_label: fr("failed", "en échec"),
      requested_by: ref("lea"),
      started_at: minutes(60 * 26),
      ended_at: minutes(60 * 26 - 9),
      steps: [],
      result: null,
      error: GYM_ERROR,
      origin: { session: "telegram:@lea_lambert", channel: "telegram" },
      delivered: null,
    },
    {
      id: "t-5e6b70",
      objective: fr("Sum up Jules's homework for the week.", "Récapituler les devoirs de Jules pour la semaine."),
      executor: "codex",
      status: "cancelled",
      status_label: CANCELLED,
      requested_by: ref("jules"),
      started_at: minutes(60 * 30),
      ended_at: minutes(60 * 30 - 1),
      steps: [],
      result: null,
      error: null,
      origin: { session: "voice:pi-bedroom", channel: "voice" },
      delivered: null,
    },
  ];
}

/** A task's label once cancelled (the admin can cancel one). */
export const CANCELLED = fr("cancelled", "annulée");

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
  c: Omit<Component, "capabilities" | "distribution" | "details"> & { capabilities?: string[] },
): Component => ({
  capabilities: [],
  distribution: null,
  details: {},
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
    nestor: { version: "0.9.0" },
    agent: { name: ASSISTANT, status: "online" },
    restart_required: false,
    pending_changes: [],
    components: [
      component({
        slot: "model",
        name: "sonnet",
        adapter: "nestor.adapters.model.openrouter",
        brand: "openrouter",
        version: "anthropic/claude-sonnet-4.6",
        health: "started",
        health_detail: fr("First token in 640 ms (today's median)", "Premier jeton en 640 ms (médiane du jour)"),
        capabilities: ["tools", "streaming"],
      }),
      component({
        slot: "model",
        name: "haiku",
        adapter: "nestor.adapters.model.openrouter",
        brand: "anthropic",
        version: "anthropic/claude-haiku-4.5",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "speech",
        name: fr("Speech recognition", "Reconnaissance vocale"),
        adapter: "nestor.adapters.speech.elevenlabs",
        brand: "elevenlabs",
        version: "scribe_v2_realtime",
        health: "started",
        health_detail: null,
        capabilities: ["partials", "en"],
      }),
      component({
        slot: "speech",
        name: fr("Speech synthesis", "Synthèse vocale"),
        adapter: "nestor.adapters.speech.elevenlabs",
        brand: "elevenlabs",
        version: "eleven_flash_v2_5",
        health: "degraded",
        health_detail: fr("High latency since 13:40 (p95 1.9 s)", "Latence élevée depuis 13:40 (p95 1,9 s)"),
      }),
      component({
        slot: "speech",
        name: fr("Speech detection", "Détection de parole"),
        adapter: "nestor.adapters.speech.silero",
        brand: "silero",
        version: "5.1",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "speech",
        name: fr("End of turn", "Fin de tour"),
        adapter: "nestor.adapters.speech.smart_turn",
        brand: "smart-turn",
        version: "3.0",
        health: "started",
        health_detail: null,
      }),
      component({
        slot: "executor",
        name: "Hermes",
        adapter: "nestor.adapters.executors.hermes",
        brand: "hermes",
        version: "0.6.1",
        health: "started",
        health_detail: ONE_TASK,
      }),
      component({
        slot: "executor",
        name: "Codex",
        adapter: "nestor.adapters.executors.codex",
        brand: "codex",
        version: "0.48",
        health: "started",
        health_detail: ONE_TASK,
      }),
      component({
        slot: "channel",
        name: fr("Voice (satellites)", "Voix (satellites)"),
        adapter: "nestor.modules.channels.voice",
        brand: "voice",
        version: PROTOCOL,
        health: "started",
        health_detail: fr("2 of 3 satellites connected", "2 satellites connectés sur 3"),
      }),
      component({
        slot: "channel",
        name: fr("Browser voice client", "Client vocal du navigateur"),
        adapter: "nestor.adapters.channels.webrtc",
        brand: "webrtc",
        version: null,
        health: "started",
        health_detail: fr("For development", "Pour le développement"),
      }),
      component({
        slot: "channel",
        name: "Telegram",
        adapter: "nestor.adapters.channels.telegram",
        brand: "telegram",
        version: "Bot API 9.2",
        health: "started",
        health_detail: "@richie_lambert_bot",
      }),
      component({
        slot: "channel",
        name: fr("Web chat", "Chat web"),
        adapter: "nestor.modules.channels.web",
        brand: "web",
        version: null,
        health: "started",
        health_detail: fr(
          "In the admin and on the household network",
          "Dans l'administration et sur le réseau du foyer",
        ),
      }),
      component({
        slot: "presence",
        name: fr("Presence from Home Assistant", "Présence par Home Assistant"),
        adapter: "nestor.adapters.home.home_assistant",
        brand: "home-assistant",
        version: "2026.10.2",
        health: "started",
        health_detail: fr("4 people tracked", "4 personnes suivies"),
      }),
      component({
        slot: "tools",
        name: fr("Home (Home Assistant MCP)", "Maison (MCP de Home Assistant)"),
        adapter: "nestor.adapters.tools.mcp",
        brand: "home-assistant",
        version: null,
        health: "started",
        health_detail: fr("5 tools", "5 outils"),
      }),
      component({
        slot: "tools",
        name: fr("Léa's recipes (MCP)", "Recettes de Léa (MCP)"),
        adapter: "nestor.adapters.tools.mcp",
        brand: "mcp",
        version: null,
        health: "unavailable",
        health_detail: fr("Connection refused by 192.168.1.20:8808", "Connexion refusée par 192.168.1.20:8808"),
      }),
      component({
        slot: "connector",
        name: "Gmail",
        adapter: "nestor.adapters.connectors.google",
        brand: "gmail",
        version: null,
        health: "degraded",
        health_detail: fr("1 account to authorise again", "1 compte à réautoriser"),
      }),
      component({
        slot: "connector",
        name: MAILBOX,
        adapter: "nestor.adapters.connectors.imap",
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
      component({
        slot: "storage",
        name: fr("Journal and state", "Journal et état"),
        adapter: "nestor.adapters.storage.sqlite",
        brand: "sqlite",
        version: "3.50.4 · WAL",
        health: "started",
        health_detail: fr("212 MB, 48,112 events", "212 Mo, 48 112 événements"),
      }),
      component({
        slot: "storage",
        name: fr("Replication", "Réplication"),
        adapter: "litestream",
        brand: "litestream",
        version: "0.5.2",
        health: "started",
        health_detail: fr("Last replica 12 s ago", "Dernière réplique il y a 12 s"),
      }),
      component({
        slot: "storage",
        name: fr("Container", "Conteneur"),
        adapter: "docker",
        brand: "docker",
        version: "nestor:0.9.0",
        health: "started",
        health_detail: null,
      }),
    ],
  };
}
