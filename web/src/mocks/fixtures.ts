/** A believable household for development and tests: Richie serving the Lambert family. */
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
  Role,
  Satellite,
  SystemInfo,
  Task,
  Tool,
  Watch,
} from "@/api";
import type { ScopeDto } from "@/api/dto";

export const ASSISTANT = "Richie";

export const minutes = (n: number, from = Date.now()) => new Date(from - n * 60_000).toISOString();
const ahead = (seconds: number) => new Date(Date.now() + seconds * 1000).toISOString();

/** The server's scopes for each role (what `/me` sends; adapt.ts groups them for the screens). */
const OWN: ScopeDto[] = ["journal.read.own", "memory.manage.own"];
const MEMBER: ScopeDto[] = [
  ...OWN,
  "household.read",
  "agent.read",
  "own.connections.manage",
  "tasks.manage.own",
  "watches.manage.own",
];
const ADMIN: ScopeDto[] = [
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
export const SCOPES: Record<Role, ScopeDto[]> = {
  owner: [...ADMIN, "accounts.owners.manage"],
  admin: ADMIN,
  member: MEMBER,
  guest: OWN,
};

export const ROLE_LABEL: Record<Role, string> = {
  owner: "propriétaire",
  admin: "administrateur",
  member: "membre",
  guest: "invité",
};

export function people(): Person[] {
  return [
    {
      id: "mathis",
      name: "Mathis",
      channels: ["voice", "telegram:@mathis_l"],
      reach: "telegram:@mathis_l",
      presence: { home: true, room: "salon", since: minutes(61) },
      account: "acc-mathis",
      account_login: "mathis",
    },
    {
      id: "lea",
      name: "Léa",
      channels: ["voice", "telegram:@lea_lambert", "web"],
      reach: "voice",
      presence: { home: false, room: null, since: minutes(205) },
      account: "acc-lea",
      account_login: "lea",
    },
    {
      id: "jules",
      name: "Jules",
      channels: ["voice"],
      reach: "voice",
      presence: { home: true, room: "salon", since: minutes(2) },
      account: null,
      account_login: null,
    },
    {
      id: "odile",
      name: "Odile",
      channels: ["telegram:@odile.m"],
      reach: "telegram:@odile.m",
      presence: { home: null, room: null, since: null },
      account: null,
      account_login: null,
    },
  ];
}

export function accounts(): Account[] {
  const account = (
    id: string,
    login: string,
    role: Role,
    person: string | null,
    person_name: string | null,
    locale: string | null,
    disabled: boolean,
    ago: number,
  ): Account => ({
    id,
    login,
    role,
    role_label: ROLE_LABEL[role],
    person,
    person_name,
    locale,
    disabled,
    created_at: minutes(ago),
    last_seen_at: disabled ? minutes(60 * 24 * 12) : minutes(login === "mathis" ? 1 : 60 * 20),
  });
  return [
    account("acc-mathis", "mathis", "owner", "mathis", "Mathis", "fr", false, 60 * 24 * 40),
    account("acc-lea", "lea", "admin", "lea", "Léa", "fr", false, 60 * 24 * 38),
    account("acc-camille", "camille", "member", null, null, null, true, 60 * 24 * 20),
  ];
}

export function invitations(): Invitation[] {
  return [
    {
      id: "inv-odile",
      role: "member",
      role_label: ROLE_LABEL.member,
      person: "odile",
      person_name: "Odile",
      status: "pending",
      status_label: "en attente",
      created_at: minutes(60 * 24 * 2),
      expires_at: ahead(60 * 60 * 24 * 5),
    },
  ];
}

const GMAIL_SETUP = `1. Ouvrez la console Google Cloud et créez un projet pour le foyer.
2. Activez l'API Gmail (API et services › Bibliothèque).
3. Dans « Écran de consentement OAuth », choisissez « Externe » et ajoutez vos adresses comme utilisateurs test.
4. Créez des identifiants « ID client OAuth », type « Application Web ».
5. Déclarez l'URI de redirection ci-dessous, puis copiez l'identifiant et le secret.`;

export function connectors(): Connector[] {
  return [
    {
      kind: "google",
      brand: "gmail",
      title: "Gmail",
      description: "Lire, chercher et rédiger des courriels ; surveiller ce qui arrive dans la boîte.",
      auth: "oauth2",
      auth_label: "OAuth",
      inbound: ["mail"],
      setup: GMAIL_SETUP,
      fields: [],
      client: { client_id: "418230-9kq3hc.apps.googleusercontent.com" },
      redirect_uri: "https://relay.nestor.dev/oauth/callback",
      relayed: true,
    },
    {
      kind: "imap",
      brand: "imap",
      title: "Boîte mail (IMAP)",
      description: "N'importe quelle boîte mail par IMAP : Fastmail, Proton Bridge, Orange, OVH…",
      auth: "secret",
      auth_label: "identifiants",
      inbound: ["mail"],
      setup:
        "Utilisez un mot de passe d'application plutôt que votre mot de passe principal quand le fournisseur le propose.",
      fields: [
        { name: "host", label: "Serveur IMAP", secret: false, optional: false, placeholder: "imap.fastmail.com" },
        { name: "port", label: "Port", secret: false, optional: true, placeholder: "993" },
        { name: "username", label: "Identifiant", secret: false, optional: false, placeholder: "lea@lambert.family" },
        { name: "password", label: "Mot de passe d'application", secret: true, optional: false, placeholder: null },
      ],
      client: null,
      redirect_uri: null,
      relayed: false,
    },
    {
      kind: "mcp",
      brand: "mcp",
      title: "Serveur MCP",
      description: "Les outils d'un serveur Model Context Protocol, local ou distant : Home Assistant, vos scripts…",
      auth: "secret",
      auth_label: "identifiants",
      inbound: [],
      setup: "Indiquez l'adresse HTTP du serveur (transport « streamable HTTP »). Le jeton est facultatif.",
      fields: [
        { name: "name", label: "Nom affiché", secret: false, optional: false, placeholder: "Notes de cuisine" },
        {
          name: "url",
          label: "Adresse du serveur",
          secret: false,
          optional: false,
          placeholder: "http://192.168.1.20:8808/mcp",
        },
        { name: "token", label: "Jeton d'accès", secret: true, optional: true, placeholder: null },
      ],
      client: null,
      redirect_uri: null,
      relayed: false,
    },
    {
      kind: "google-calendar",
      brand: "google-calendar",
      title: "Google Agenda",
      description: "Consulter les agendas du foyer et y ajouter des événements.",
      auth: "oauth2",
      auth_label: "OAuth",
      inbound: [],
      setup: GMAIL_SETUP.replace("l'API Gmail", "l'API Google Calendar"),
      fields: [],
      client: null,
      redirect_uri: "https://relay.nestor.dev/oauth/callback",
      relayed: true,
    },
  ];
}

export function connections(): Connection[] {
  return [
    {
      id: "c-gmail-mathis",
      kind: "google",
      brand: "gmail",
      title: "Gmail",
      account: "mathis.lambert27@gmail.com",
      owner: "mathis",
      status: "needs_reauth",
      status_label: "à réautoriser",
      status_reason: "Google a refusé le renouvellement du jeton (invalid_grant).",
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
      title: "Boîte mail (IMAP)",
      account: "lea@lambert.family",
      owner: "lea",
      status: "connected",
      status_label: "connectée",
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
      title: "Serveur MCP",
      account: "Home Assistant · maison",
      owner: null,
      status: "connected",
      status_label: "connectée",
      status_reason: null,
      confirm_writes: false,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 30),
      last_used_at: minutes(61),
      calls_today: 1,
      watches: 0,
    },
    {
      id: "c-mcp-recettes",
      kind: "mcp",
      brand: "mcp",
      title: "Serveur MCP",
      account: "Recettes de Léa",
      owner: "lea",
      status: "error",
      status_label: "erreur",
      status_reason: "Connexion refusée par http://192.168.1.20:8808/mcp.",
      confirm_writes: true,
      disabled_tools: [],
      created_at: minutes(60 * 24 * 3),
      last_used_at: minutes(6),
      calls_today: 1,
      watches: 0,
    },
  ];
}

export function tools(kind: string): Tool[] {
  if (kind === "google" || kind === "imap") {
    return [
      {
        name: "mail_search",
        description: "Chercher des courriels par expéditeur, sujet ou date.",
        risk: "read",
        risk_label: "lecture",
        enabled: true,
      },
      {
        name: "mail_read",
        description: "Lire un courriel et ses pièces jointes texte.",
        risk: "read",
        risk_label: "lecture",
        enabled: true,
      },
      {
        name: "mail_draft",
        description: "Préparer un brouillon de réponse, sans l'envoyer.",
        risk: "write",
        risk_label: "écriture",
        enabled: true,
      },
      {
        name: "mail_label",
        description: "Classer un courriel (libellés, archivage).",
        risk: "write",
        risk_label: "écriture",
        enabled: false,
      },
      {
        name: "mail_send",
        description: "Envoyer un courriel au nom de la personne.",
        risk: "sensitive",
        risk_label: "sensible",
        enabled: false,
      },
    ];
  }
  return [
    {
      name: "ha_get_state",
      description: "Lire l'état d'un appareil ou d'un capteur.",
      risk: "read",
      risk_label: "lecture",
      enabled: true,
    },
    {
      name: "ha_list_areas",
      description: "Lister les pièces et leurs appareils.",
      risk: "read",
      risk_label: "lecture",
      enabled: true,
    },
    {
      name: "ha_turn_on",
      description: "Allumer une lumière, une prise ou une scène.",
      risk: "write",
      risk_label: "écriture",
      enabled: true,
    },
    {
      name: "ha_turn_off",
      description: "Éteindre une lumière, une prise ou une scène.",
      risk: "write",
      risk_label: "écriture",
      enabled: true,
    },
    {
      name: "ha_unlock",
      description: "Déverrouiller une serrure connectée.",
      risk: "sensitive",
      risk_label: "sensible",
      enabled: false,
    },
  ];
}

const cap = (name: string, label: string): Capability => ({ name, label });
const MIC = cap("audio.capture", "micro");
const SPEAKER = cap("audio.playback", "haut-parleur");
const VAD = cap("audio.speech_activity", "détection de parole");
const PEOPLE = cap("vision.person_detection", "détection de personnes (sans image transmise)");
const FACE = cap("expression.emotion", "expressions");
const HEAD = cap("motion.head", "mouvements de tête");

const IDENTIFY = cap("device.identify", "se signaler (lumière, mouvement ou son)");

/** The pairing methods, as Nestor's catalogue words them (`labels.ftl`), in the recommended order. */
export const METHODS: PairingMethod[] = [
  {
    id: "device_code.display",
    proof: "device_code",
    label: "Code sur son écran",
    hint: "Saisissez le code affiché par l'appareil.",
  },
  {
    id: "device_code.speech",
    proof: "device_code",
    label: "Code dit à voix haute",
    hint: "Saisissez le code que dit l'appareil.",
  },
  {
    id: "enrollment.qr",
    proof: "enrollment_code",
    label: "QR code",
    hint: "Montrez le QR code à la caméra de l'appareil.",
  },
  {
    id: "enrollment.input",
    proof: "enrollment_code",
    label: "Code saisi sur l'appareil",
    hint: "Saisissez ce code sur l'appareil.",
  },
  {
    id: "enrollment.provisioning",
    proof: "enrollment_code",
    label: "Configuration",
    hint: "Donnez à l'appareil l'adresse d'appairage, dans NESTOR_PAIRING_URI ou ses réglages.",
  },
];
const method = (id: PairingMethodId) => METHODS.find((m) => m.id === id) as PairingMethod;

export function pairing(): PairingRequest[] {
  return [
    {
      id: "pair-7f3a",
      device: { id: "reachy-mini-entree", model: "Reachy Mini", room: "entrée", brand: "reachy", sdk: "python" },
      capabilities: [MIC, SPEAKER, VAD, PEOPLE, FACE, HEAD, IDENTIFY],
      methods: [method("device_code.speech"), method("enrollment.provisioning")],
      recommended_method: "device_code.speech",
      can_identify: true,
      expires_at: ahead(4 * 60 + 12),
    },
    {
      id: "pair-91c0",
      device: { id: "esp32-cuisine", model: "ESP32-S3 Box", room: "cuisine", brand: "espressif", sdk: "cpp" },
      capabilities: [MIC, SPEAKER],
      methods: [method("device_code.display"), method("enrollment.input"), method("enrollment.provisioning")],
      recommended_method: "device_code.display",
      can_identify: false,
      expires_at: ahead(8 * 60 + 40),
    },
  ];
}

/** A device turning up for an addition made with a device code method. */
export function arriving(pairingId: string, room: string | null): PairingRequest {
  return {
    id: pairingId,
    device: {
      id: "reachy-mini-veranda",
      model: "Reachy Mini",
      room: room ?? "véranda",
      brand: "reachy",
      sdk: "python",
    },
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
      id: "reachy-salon",
      name: "Reachy du salon",
      can_identify: true,
      model: "Reachy Mini",
      room: "salon",
      capabilities: [MIC, SPEAKER, VAD, PEOPLE, FACE, HEAD],
      paired_at: minutes(60 * 24 * 26),
      approved_by: "mathis",
      approved_by_name: "Mathis",
      connected: true,
      last_seen_at: minutes(0.2),
      brand: "reachy",
      sdk: "python",
      sdk_version: "0.4.2",
    },
    {
      id: "reachy-bureau",
      name: null,
      can_identify: true,
      model: "Reachy Mini",
      room: "bureau",
      capabilities: [MIC, SPEAKER, VAD, FACE],
      paired_at: minutes(60 * 24 * 20),
      approved_by: "mathis",
      approved_by_name: "Mathis",
      connected: false,
      last_seen_at: minutes(97),
      brand: "reachy",
      sdk: "python",
      sdk_version: "0.4.1",
    },
    {
      id: "pi-chambre-jules",
      name: "Enceinte de Jules",
      can_identify: false,
      model: "Raspberry Pi 5 · ReSpeaker",
      room: "chambre de Jules",
      capabilities: [MIC, SPEAKER],
      paired_at: minutes(60 * 24 * 12),
      approved_by: "lea",
      approved_by_name: "Léa",
      connected: true,
      last_seen_at: minutes(0.5),
      brand: "raspberry-pi",
      sdk: "python",
      sdk_version: "0.4.2",
    },
  ];
}

export function tasks(): Task[] {
  return [
    {
      id: "t-4410aa",
      objective: "Préparer le dossier de remboursement de la mutuelle pour les lunettes de Jules.",
      executor: "hermes",
      status: "running",
      status_label: "en cours",
      requested_by: "mathis",
      started_at: minutes(30.9),
      ended_at: null,
      steps: ["Formulaire de la mutuelle téléchargé.", "En attente de la facture : Gmail est à reconnecter."],
      result: null,
      error: null,
      origin: { session: "s-mutuelle", channel: "telegram" },
      delivered: null,
    },
    {
      id: "t-88b07e",
      objective: "Préparer la liste de courses de la semaine à partir des menus de Léa.",
      executor: "codex",
      status: "running",
      status_label: "en cours",
      requested_by: "lea",
      started_at: minutes(11.9),
      ended_at: null,
      steps: ["Lecture du serveur MCP « Recettes de Léa »."],
      result: null,
      error: null,
      origin: { session: "s-courses", channel: "web" },
      delivered: null,
    },
    {
      id: "t-3f2a1c",
      objective: "Comparer trois offres d'électricité verte et résumer les écarts de prix annuels.",
      executor: "hermes",
      status: "completed",
      status_label: "terminée",
      requested_by: "mathis",
      started_at: minutes(351.6),
      ended_at: minutes(251),
      steps: [
        "Lecture des deux dernières factures : 6 800 kWh/an, heures creuses.",
        "Grilles tarifaires d'Ekwateur, Enercoop et Ilek récupérées.",
        "Calcul sur un an, abonnement compris.",
      ],
      result: "Ilek est 38 € moins cher par an ; Enercoop 112 € plus cher ; Ekwateur au même prix.",
      error: null,
      origin: { session: "s-elec", channel: "telegram" },
      delivered: { at: minutes(250.4), channel: "voice", room: "bureau" },
    },
    {
      id: "t-a04f12",
      objective: "Résilier l'abonnement à la salle de sport.",
      executor: "hermes",
      status: "failed",
      status_label: "en échec",
      requested_by: "lea",
      started_at: minutes(60 * 26),
      ended_at: minutes(60 * 26 - 9),
      steps: [],
      result: null,
      error: "Le site demande une connexion par SMS : impossible sans Léa.",
      origin: { session: null, channel: "telegram" },
      delivered: null,
    },
    {
      id: "t-5e6b70",
      objective: "Récapituler les devoirs de Jules pour la semaine.",
      executor: "codex",
      status: "cancelled",
      status_label: "annulée",
      requested_by: "jules",
      started_at: minutes(60 * 30),
      ended_at: minutes(60 * 30 - 1),
      steps: [],
      result: null,
      error: null,
      origin: { session: null, channel: "voice" },
      delivered: null,
    },
  ];
}

export function watches(): Watch[] {
  return [
    {
      id: "w-9d41",
      what: "Le colis Vinted de Léa : prévenir quand il est disponible en point relais.",
      owner: "lea",
      kinds: ["mail"],
      keywords: ["Mondial Relay", "Vinted", "disponible"],
      once: false,
      created_at: minutes(60 * 28),
      until: ahead(60 * 60 * 24 * 6),
      origin: { session: "s-hier", channel: "telegram" },
      triggered: 1,
      last_triggered_at: minutes(230),
    },
    {
      id: "w-2b77",
      what: "Les messages de l'école de Jules.",
      owner: null,
      kinds: ["mail"],
      keywords: ["école Jean-Moulin", "ENT"],
      once: false,
      created_at: minutes(60 * 24 * 14),
      until: null,
      origin: null,
      triggered: 7,
      last_triggered_at: minutes(96),
    },
  ];
}

export function memories(): Memory[] {
  const m = (
    id: string,
    text: string,
    about: string | null,
    told_by: string | null,
    channel: string | null,
    ago: number,
    learnt: string | null = null,
    session: string | null = null,
  ): Memory => ({
    id,
    text,
    about,
    told_by,
    channel,
    updated_at: minutes(ago),
    learnt_event: learnt,
    session,
    editable: true,
  });
  return [
    m("m-01", "Jules est allergique aux arachides.", "jules", "lea", "voice", 60 * 24 * 18),
    m(
      "m-02",
      "Mathis préfère qu'on ne lui parle pas avant 8 h, sauf urgence.",
      "mathis",
      "mathis",
      "telegram",
      60 * 24 * 7,
    ),
    m(
      "m-03",
      "Le code du portail est donné de vive voix uniquement, jamais par écrit.",
      null,
      "mathis",
      "voice",
      60 * 24 * 30,
    ),
    m("m-04", "Odile vient déjeuner le premier dimanche de chaque mois.", "odile", "lea", "voice", 60 * 30),
    m("m-05", "Léa fait du yoga le mardi soir, de 19 h à 20 h 30.", "lea", "lea", "telegram", 60 * 24 * 4),
    m(
      "m-06",
      "La chaudière est révisée chaque année en octobre par Engie Home Services.",
      null,
      "mathis",
      "voice",
      60 * 24 * 60,
    ),
    m(
      "m-07",
      "Jules a entraînement de handball le mercredi à 15 h.",
      "jules",
      "jules",
      "voice",
      149.4,
      "LEARNT",
      "s-jules",
    ),
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

export function system(): SystemInfo {
  return {
    nestor: { version: "0.9.0" },
    agent: { name: ASSISTANT, status: "online" },
    restart_required: false,
    pending_changes: [],
    components: [
      component({
        id: "model",
        slot: "model",
        name: "Claude Sonnet 4.6",
        adapter: "nestor.adapters.model.openrouter",
        brand: "openrouter",
        version: "anthropic/claude-sonnet-4.6",
        health: "ok",
        health_detail: "Premier jeton en 640 ms (médiane du jour)",
        capabilities: ["tools", "streaming"],
      }),
      component({
        id: "triage",
        slot: "model",
        name: "Claude Haiku 4.5 (tri des veilles)",
        adapter: "nestor.adapters.model.openrouter",
        brand: "anthropic",
        version: "anthropic/claude-haiku-4.5",
        health: "ok",
        health_detail: null,
      }),
      component({
        id: "stt",
        slot: "speech",
        name: "Reconnaissance vocale",
        adapter: "nestor.adapters.speech.elevenlabs",
        brand: "elevenlabs",
        version: "scribe_v2_realtime",
        health: "ok",
        health_detail: null,
        capabilities: ["partials", "fr"],
      }),
      component({
        id: "tts",
        slot: "speech",
        name: "Synthèse vocale",
        adapter: "nestor.adapters.speech.elevenlabs",
        brand: "elevenlabs",
        version: "eleven_flash_v2_5",
        health: "degraded",
        health_detail: "Latence élevée depuis 13:40 (p95 1,9 s)",
      }),
      component({
        id: "vad",
        slot: "speech",
        name: "Détection de parole",
        adapter: "nestor.adapters.speech.silero",
        brand: "silero",
        version: "5.1",
        health: "ok",
        health_detail: null,
      }),
      component({
        id: "turn",
        slot: "speech",
        name: "Fin de tour",
        adapter: "nestor.adapters.speech.smart_turn",
        brand: "smart-turn",
        version: "3.0",
        health: "ok",
        health_detail: null,
      }),
      component({
        id: "hermes",
        slot: "executor",
        name: "Hermes",
        adapter: "nestor.adapters.executors.hermes",
        brand: "hermes",
        version: "0.6.1",
        health: "ok",
        health_detail: "1 tâche en cours",
      }),
      component({
        id: "codex",
        slot: "executor",
        name: "Codex",
        adapter: "nestor.adapters.executors.codex",
        brand: "codex",
        version: "0.48",
        health: "ok",
        health_detail: "1 tâche en cours",
      }),
      component({
        id: "ch-voice",
        slot: "channel",
        name: "Voix (satellites)",
        adapter: "nestor.modules.channels.voice",
        brand: "voice",
        version: "nestor.satellite/1",
        health: "ok",
        health_detail: "2 satellites connectés sur 3",
      }),
      component({
        id: "ch-webrtc",
        slot: "channel",
        name: "Client vocal du navigateur",
        adapter: "nestor.adapters.channels.webrtc",
        brand: "webrtc",
        version: null,
        health: "ok",
        health_detail: "Pour le développement",
      }),
      component({
        id: "ch-telegram",
        slot: "channel",
        name: "Telegram",
        adapter: "nestor.adapters.channels.telegram",
        brand: "telegram",
        version: "Bot API 9.2",
        health: "ok",
        health_detail: "@richie_lambert_bot",
      }),
      component({
        id: "ch-web",
        slot: "channel",
        name: "Chat web",
        adapter: "nestor.modules.channels.web",
        brand: "web",
        version: null,
        health: "ok",
        health_detail: "Dans l'administration et sur le réseau du foyer",
      }),
      component({
        id: "presence",
        slot: "presence",
        name: "Présence par Home Assistant",
        adapter: "nestor.adapters.home.home_assistant",
        brand: "home-assistant",
        version: "2026.10.2",
        health: "ok",
        health_detail: "4 personnes suivies",
      }),
      component({
        id: "tools-ha",
        slot: "tools",
        name: "Maison (MCP de Home Assistant)",
        adapter: "nestor.adapters.tools.mcp",
        brand: "home-assistant",
        version: null,
        health: "ok",
        health_detail: "5 outils",
      }),
      component({
        id: "tools-recettes",
        slot: "tools",
        name: "Recettes de Léa (MCP)",
        adapter: "nestor.adapters.tools.mcp",
        brand: "mcp",
        version: null,
        health: "down",
        health_detail: "Connexion refusée par 192.168.1.20:8808",
      }),
      component({
        id: "cn-google",
        slot: "connector",
        name: "Gmail",
        adapter: "nestor.adapters.connectors.google",
        brand: "gmail",
        version: null,
        health: "degraded",
        health_detail: "1 compte à réautoriser",
      }),
      component({
        id: "cn-imap",
        slot: "connector",
        name: "Boîte mail (IMAP)",
        adapter: "nestor.adapters.connectors.imap",
        brand: "imap",
        version: null,
        health: "ok",
        health_detail: null,
      }),
      component({
        id: "sat-salon",
        slot: "satellite",
        name: "reachy-salon",
        adapter: "SDK Python 0.4.2",
        brand: "reachy",
        version: "nestor.satellite/1",
        health: "ok",
        health_detail: "salon",
      }),
      component({
        id: "sat-bureau",
        slot: "satellite",
        name: "reachy-bureau",
        adapter: "SDK Python 0.4.1",
        brand: "reachy",
        version: "nestor.satellite/1",
        health: "down",
        health_detail: "Hors ligne depuis 97 min",
      }),
      component({
        id: "sat-jules",
        slot: "satellite",
        name: "pi-chambre-jules",
        adapter: "SDK Python 0.4.2",
        brand: "raspberry-pi",
        version: "nestor.satellite/1",
        health: "ok",
        health_detail: "chambre de Jules",
      }),
      component({
        id: "db",
        slot: "storage",
        name: "Journal et état",
        adapter: "nestor.adapters.storage.sqlite",
        brand: "sqlite",
        version: "3.50.4 · WAL",
        health: "ok",
        health_detail: "212 Mo, 48 112 événements",
      }),
      component({
        id: "backup",
        slot: "storage",
        name: "Réplication",
        adapter: "litestream",
        brand: "litestream",
        version: "0.5.2",
        health: "ok",
        health_detail: "Dernière réplique il y a 12 s",
      }),
      component({
        id: "runtime",
        slot: "storage",
        name: "Conteneur",
        adapter: "docker",
        brand: "docker",
        version: "nestor:0.9.0",
        health: "ok",
        health_detail: null,
      }),
    ],
  };
}

export const KIND_LABELS: Record<string, string> = {
  conversation: "Conversations",
  delivery: "Prises de parole",
  tool: "Outils",
  task: "Tâches",
  watch: "Veilles",
  memory: "Souvenirs",
  connection: "Connexions",
  presence: "Présence",
  satellite: "Satellites",
  observation: "Observations",
};

export { LIVE } from "./day";
