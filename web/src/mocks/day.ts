/**
 * A day of Richie at the Lambert's, as the journal records it: linked events that the admin turns
 * into threads (a conversation and its tool calls) and chains (a watch triggered → announced →
 * followed up; a task started → progressing → delivered). Times are minutes before "now".
 */
import type { EventLinks, JournalEvent, JournalItem, Tone } from "@/api";
import { type Draft as LiveDraft, toItem } from "./messages";

interface Draft {
  ago: number; // minutes before now
  type: string;
  kind: string;
  title: string;
  detail?: string;
  reason?: string;
  people?: string[];
  channels?: string[];
  room?: string | null;
  tone?: Tone;
  links?: EventLinks;
  cause?: string | null;
  outcome?: { ok: boolean; duration_s: number | null } | null;
  tool?: string | null;
  brand?: string | null;
  record?: Record<string, unknown>;
}

const VOICE = "voice";

export function day(now = Date.now()): JournalEvent[] {
  let seq = 0;
  const events: JournalEvent[] = [];
  const at = (ago: number) => new Date(now - ago * 60_000).toISOString();

  function ev(d: Draft): string {
    const id = `e-${String(++seq).padStart(4, "0")}`;
    const item: JournalItem = toItem({
      id,
      at: at(d.ago),
      type: d.type,
      kind: d.kind,
      title: d.title,
      detail: d.detail ?? "",
      reason: d.reason && d.reason !== "model_slow" ? d.reason : undefined,
      people: d.people ?? [],
      channels: d.channels ?? [],
      room: d.room ?? null,
      tone: d.tone ?? "normal",
      links: d.links ?? {},
      cause: d.cause ?? null,
      outcome: d.outcome ?? null,
      tool: d.tool ?? null,
      brand: d.brand ?? d.channels?.[0] ?? null,
      uid: id,
      kind_label: "",
    });
    const record = {
      type: d.type,
      version: 1,
      at: item.at,
      ...(d.record ?? {}),
      ...Object.fromEntries(Object.entries(d.links ?? {}).map(([k, v]) => [`${k}_id`, v])),
    };
    events.push({ ...item, record });
    return id;
  }

  // -- earlier days: a quieter background, single events ------------------------------------------
  const BACKGROUND: Omit<Draft, "ago">[] = [
    {
      type: "home.presence_changed",
      kind: "presence",
      title: "Mathis est dans la pièce « cuisine »",
      people: ["mathis"],
      room: "cuisine",
      record: { person: "mathis", home: true, room: "cuisine" },
    },
    {
      type: "satellites.person_detected",
      kind: "observation",
      title: "1 personne vue par reachy-salon (pièce « salon »)",
      detail: "Confiance : 91 %",
      room: "salon",
      links: { satellite: "reachy-salon" },
      record: { count: 1, confidence: 0.91 },
    },
    {
      type: "conversation.user_turn",
      kind: "conversation",
      title: "Odile a dit",
      detail: "Bonjour Richie, rappelle à Léa que je viens dimanche.",
      people: ["odile"],
      channels: ["telegram"],
      links: { session: "s-odile" },
      record: { text: "Bonjour Richie, rappelle à Léa que je viens dimanche." },
    },
    {
      type: "conversation.assistant_turn",
      kind: "conversation",
      title: "Richie a répondu",
      detail: "Bien reçu, je lui dirai ce soir.",
      channels: ["telegram"],
      links: { session: "s-odile" },
    },
    {
      type: "satellites.speech_activity",
      kind: "observation",
      title: "Parole détectée près de reachy-bureau (pièce « bureau »)",
      room: "bureau",
      links: { satellite: "reachy-bureau" },
    },
    {
      type: "home.presence_changed",
      kind: "presence",
      title: "Jules est dans la pièce « chambre de Jules »",
      people: ["jules"],
      room: "chambre de Jules",
    },
    {
      type: "tools.tool_called",
      kind: "tool",
      title: "Outil ha_get_state appelé",
      detail: '{"entity_id": "sensor.temperature_salon"}',
      tool: "ha_get_state",
      brand: "home-assistant",
      links: { call: "c-bg", connection: "c-mcp-ha" },
    },
    {
      type: "tools.tool_completed",
      kind: "tool",
      title: "Outil ha_get_state terminé en 0,3 s",
      detail: "19,5 °C",
      tool: "ha_get_state",
      brand: "home-assistant",
      outcome: { ok: true, duration_s: 0.3 },
      links: { call: "c-bg", connection: "c-mcp-ha" },
    },
  ];
  for (let i = 0; i < 96; i++) {
    const base = BACKGROUND[i % BACKGROUND.length] as Omit<Draft, "ago">;
    const ago = 60 * 26 + i * 37;
    const links = { ...base.links };
    if (links.session) links.session = `${links.session}-${Math.floor(i / BACKGROUND.length)}`;
    if (links.call) links.call = `${links.call}-${Math.floor(i / BACKGROUND.length)}`;
    ev({ ...base, ago, links });
  }

  // -- yesterday: a watch is born, a task fails ---------------------------------------------------
  const born = ev({
    ago: 60 * 28,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Léa a dit",
    detail: "Préviens-moi quand mon colis Vinted arrive au point relais.",
    people: ["lea"],
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier" },
  });
  ev({
    ago: 60 * 28 - 0.2,
    type: "initiative.watch_created",
    kind: "watch",
    title: "Veille créée : le colis Vinted de Léa",
    detail: "Mots-clés : Mondial Relay, Vinted, disponible",
    people: ["lea"],
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier", watch: "w-9d41" },
    cause: born,
  });
  ev({
    ago: 60 * 28 - 0.3,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "Je surveille ta boîte : je te préviens dès qu'il est disponible.",
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier" },
  });
  ev({
    ago: 60 * 26 - 9,
    type: "cognition.task_ended",
    kind: "task",
    title: "Tâche a04f12 en échec (9 min)",
    detail: "Le site demande une connexion par SMS : impossible sans Léa.",
    tone: "warning",
    brand: "hermes",
    outcome: { ok: false, duration_s: 540 },
    links: { task: "t-a04f12" },
  });

  // -- this morning -------------------------------------------------------------------------------
  ev({
    ago: 412,
    type: "home.presence_changed",
    kind: "presence",
    title: "Mathis est dans la pièce « cuisine »",
    people: ["mathis"],
    room: "cuisine",
    record: { person: "mathis", home: true, room: "cuisine" },
  });
  ev({
    ago: 405,
    type: "home.presence_changed",
    kind: "presence",
    title: "Léa est dans la pièce « salon »",
    people: ["lea"],
    room: "salon",
  });

  // a voice exchange in the living room, with a tool call
  const s1 = { session: "s-matin" };
  const u1 = ev({
    ago: 398,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Léa a dit",
    detail: "Richie, qu'est-ce que j'ai aujourd'hui ?",
    people: ["lea"],
    channels: [VOICE],
    room: "salon",
    links: { ...s1, turn: "u-1", satellite: "reachy-salon" },
    record: { text: "Richie, qu'est-ce que j'ai aujourd'hui ?", speaker: "lea", speaker_confidence: 0.88 },
  });
  ev({
    ago: 397.9,
    type: "tools.tool_called",
    kind: "tool",
    title: "Outil calendar_list appelé",
    detail: '{"day": "today", "calendar": "lea"}',
    tool: "calendar_list",
    brand: "google-calendar",
    people: ["lea"],
    channels: [VOICE],
    links: { ...s1, turn: "u-1", call: "k-1" },
    cause: u1,
  });
  ev({
    ago: 397.8,
    type: "tools.tool_completed",
    kind: "tool",
    title: "Outil calendar_list terminé en 0,7 s",
    detail: "2 événements : « Point équipe » 10:00, « Yoga » 19:00",
    tool: "calendar_list",
    brand: "google-calendar",
    outcome: { ok: true, duration_s: 0.7 },
    links: { ...s1, turn: "u-1", call: "k-1" },
  });
  ev({
    ago: 397.7,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "Un point d'équipe à 10 h, puis ton yoga à 19 h. Rien d'autre.",
    channels: [VOICE],
    room: "salon",
    links: { ...s1, turn: "u-1" },
    record: { latency_ms: 1180, model: "claude-sonnet-4.6" },
  });

  // Mathis asks on Telegram for a long task: a thread and a chain at once
  const s2 = { session: "s-elec" };
  const u2 = ev({
    ago: 352,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Mathis a dit",
    detail: "Tu peux comparer les offres d'électricité verte ? Base-toi sur mes dernières factures.",
    people: ["mathis"],
    channels: ["telegram"],
    links: { ...s2, turn: "u-2" },
  });
  ev({
    ago: 351.9,
    type: "tools.tool_called",
    kind: "tool",
    title: "Outil mail_search appelé",
    detail: '{"query": "from:edf facture", "limit": 2}',
    tool: "mail_search",
    brand: "gmail",
    people: ["mathis"],
    channels: ["telegram"],
    links: { ...s2, turn: "u-2", call: "k-2", connection: "c-gmail-mathis" },
    cause: u2,
  });
  ev({
    ago: 351.8,
    type: "tools.tool_completed",
    kind: "tool",
    title: "Outil mail_search terminé en 0,8 s",
    detail: "2 courriels : « Votre facture de septembre », « Votre facture d'août ».",
    tool: "mail_search",
    brand: "gmail",
    outcome: { ok: true, duration_s: 0.8 },
    links: { ...s2, turn: "u-2", call: "k-2", connection: "c-gmail-mathis" },
  });
  const started = ev({
    ago: 351.6,
    type: "cognition.task_started",
    kind: "task",
    title: "Tâche 3f2a1c confiée à hermes",
    detail: "Comparer trois offres d'électricité verte et résumer les écarts de prix annuels.",
    people: ["mathis"],
    channels: ["telegram"],
    brand: "hermes",
    links: { ...s2, turn: "u-2", task: "t-3f2a1c" },
    cause: u2,
  });
  ev({
    ago: 351.5,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "C'est parti : je te préviens dès que j'ai les chiffres.",
    channels: ["telegram"],
    links: { ...s2, turn: "u-2" },
  });
  ev({
    ago: 340,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 3f2a1c : nouvelle étape",
    detail: "Lecture des deux dernières factures : 6 800 kWh/an, heures creuses.",
    brand: "hermes",
    links: { task: "t-3f2a1c" },
    cause: started,
  });
  ev({
    ago: 318,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 3f2a1c : nouvelle étape",
    detail: "Grilles tarifaires d'Ekwateur, Enercoop et Ilek récupérées.",
    brand: "hermes",
    links: { task: "t-3f2a1c" },
  });
  ev({
    ago: 290,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 3f2a1c : nouvelle étape",
    detail: "Calcul sur un an, abonnement compris.",
    brand: "hermes",
    links: { task: "t-3f2a1c" },
  });
  const ended = ev({
    ago: 251,
    type: "cognition.task_ended",
    kind: "task",
    title: "Tâche 3f2a1c terminée (1 h 41)",
    detail: "Ilek est 38 € moins cher par an ; Enercoop 112 € plus cher ; Ekwateur au même prix.",
    brand: "hermes",
    outcome: { ok: true, duration_s: 6060 },
    links: { task: "t-3f2a1c" },
  });
  ev({
    ago: 250.6,
    type: "initiative.delivery_considered",
    kind: "delivery",
    title: "Décision de parler à Mathis — tâche 3f2a1c terminée",
    reason: "Mathis est dans la pièce « bureau »",
    detail: "Prévu : à voix haute sur voice (bureau)",
    people: ["mathis"],
    channels: [VOICE],
    room: "bureau",
    tone: "decision",
    links: { task: "t-3f2a1c", delivery: "d-1" },
    cause: ended,
    record: { policy: "presence", spoken: "voice:bureau", written: null },
  });
  ev({
    ago: 250.4,
    type: "initiative.delivered",
    kind: "delivery",
    title: "Message transmis à voix haute — tâche 3f2a1c",
    detail: "« Mathis, j'ai fini la comparaison : Ilek te ferait gagner 38 € par an. »",
    people: ["mathis"],
    channels: [VOICE],
    room: "bureau",
    links: { task: "t-3f2a1c", delivery: "d-1", satellite: "reachy-bureau" },
  });

  // the parcel: a watch triggered, announced by voice, then followed up in writing
  const w = { watch: "w-9d41" };
  const trig = ev({
    ago: 230,
    type: "initiative.watch_triggered",
    kind: "watch",
    title: "Veille 9d41 déclenchée par « Votre colis est disponible »",
    detail: "Mondial Relay : colis disponible au Tabac de la Place jusqu'au 6 nov.",
    people: ["lea"],
    brand: "imap",
    links: { ...w, connection: "c-imap-lea" },
    record: { item: { kind: "mail", from: "noreply@mondialrelay.fr", subject: "Votre colis est disponible" } },
  });
  ev({
    ago: 229.8,
    type: "initiative.watch_triaged",
    kind: "watch",
    title: "Tri : pertinent pour Léa",
    detail: "Le colis Vinted attendu est arrivé au point relais ; rien d'urgent.",
    people: ["lea"],
    links: w,
    cause: trig,
    record: { verdict: "relevant", urgent: false, model: "claude-haiku-4.5" },
  });
  ev({
    ago: 229.6,
    type: "initiative.delivery_considered",
    kind: "delivery",
    title: "Décision de parler à Léa — veille 9d41",
    reason: "Léa est dans la pièce « salon »",
    detail: "Prévu : à voix haute sur voice (salon)",
    people: ["lea"],
    channels: [VOICE],
    room: "salon",
    tone: "decision",
    links: { ...w, delivery: "d-2" },
  });
  ev({
    ago: 229.4,
    type: "initiative.delivered",
    kind: "delivery",
    title: "Message transmis à voix haute — veille 9d41",
    detail: "« Léa, ton colis Vinted t'attend au Tabac de la Place. »",
    people: ["lea"],
    channels: [VOICE],
    room: "salon",
    links: { ...w, delivery: "d-2", satellite: "reachy-salon" },
  });
  ev({
    ago: 205,
    type: "home.presence_changed",
    kind: "presence",
    title: "Léa n'est plus à la maison",
    people: ["lea"],
  });
  ev({
    ago: 199.6,
    type: "initiative.delivery_considered",
    kind: "delivery",
    title: "Décision de parler à Léa — veille 9d41 (relance)",
    reason: "pas de réponse depuis 30 min, et Léa n'est pas à la maison",
    detail: "Prévu : par écrit sur telegram",
    people: ["lea"],
    channels: ["telegram"],
    tone: "decision",
    links: { ...w, delivery: "d-2" },
  });
  ev({
    ago: 199.4,
    type: "initiative.delivered",
    kind: "delivery",
    title: "Message transmis par écrit — veille 9d41 (relance)",
    detail: "« Ton colis est au Tabac de la Place jusqu'au 6 novembre. »",
    people: ["lea"],
    channels: ["telegram"],
    links: { ...w, delivery: "d-2" },
  });
  const s3 = { session: "s-colis" };
  ev({
    ago: 190,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Léa a dit",
    detail: "Merci ! J'irai le chercher en rentrant.",
    people: ["lea"],
    channels: ["telegram"],
    links: { ...s3, turn: "u-3", watch: "w-9d41" },
  });
  ev({
    ago: 189.9,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "Parfait. Je garde la veille ouverte jusqu'à ce qu'il soit retiré.",
    channels: ["telegram"],
    links: { ...s3, turn: "u-3" },
  });

  // Gmail stops answering: a failed tool call, then the connection needs a reconnect
  ev({
    ago: 171,
    type: "tools.tool_called",
    kind: "tool",
    title: "Outil mail_search appelé",
    detail: '{"query": "mutuelle remboursement", "limit": 5}',
    tool: "mail_search",
    brand: "gmail",
    people: ["mathis"],
    links: { call: "k-3", connection: "c-gmail-mathis", task: "t-4410aa" },
  });
  const failed = ev({
    ago: 170.9,
    type: "tools.tool_completed",
    kind: "tool",
    title: "Outil mail_search en échec",
    detail: "Google a refusé le jeton d'accès (invalid_grant).",
    tool: "mail_search",
    brand: "gmail",
    tone: "warning",
    outcome: { ok: false, duration_s: 1.2 },
    links: { call: "k-3", connection: "c-gmail-mathis", task: "t-4410aa" },
  });
  ev({
    ago: 170.8,
    type: "connectors.connection_changed",
    kind: "connection",
    title: "Connexion mathis.lambert27@gmail.com à réautoriser",
    detail: "Google a refusé le renouvellement du jeton : reconnectez le compte.",
    people: ["mathis"],
    brand: "gmail",
    tone: "warning",
    links: { connection: "c-gmail-mathis" },
    cause: failed,
  });

  // Jules interrupts, then teaches Richie something
  const s4 = { session: "s-jules" };
  ev({
    ago: 150,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Jules a dit",
    detail: "Richie, c'est quand mon entraînement de hand ?",
    people: ["jules"],
    channels: [VOICE],
    room: "chambre de Jules",
    links: { ...s4, turn: "u-4", satellite: "pi-chambre-jules" },
  });
  ev({
    ago: 149.9,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu (interrompu)",
    detail: "Mercredi à 14 h, comme chaque semaine. N'oublie pas ta gourde et…",
    channels: [VOICE],
    room: "chambre de Jules",
    links: { ...s4, turn: "u-4" },
    record: { interrupted: true },
  });
  ev({
    ago: 149.85,
    type: "conversation.answer_cut",
    kind: "conversation",
    title: "Réponse coupée par Jules",
    detail: "Entendu : « stop, c'est bon »",
    people: ["jules"],
    channels: [VOICE],
    room: "chambre de Jules",
    links: { ...s4, turn: "u-4" },
  });
  const u5 = ev({
    ago: 149.5,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Jules a dit",
    detail: "Et tu peux retenir que maintenant c'est à 15 h ?",
    people: ["jules"],
    channels: [VOICE],
    room: "chambre de Jules",
    links: { ...s4, turn: "u-5" },
  });
  ev({
    ago: 149.4,
    type: "memory.recorded",
    kind: "memory",
    title: "Souvenir enregistré",
    detail: "Jules a entraînement de handball le mercredi à 15 h.",
    people: ["jules"],
    channels: [VOICE],
    links: { ...s4, turn: "u-5", memory: "m-07" },
    cause: u5,
  });
  ev({
    ago: 149.3,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "C'est noté : mercredi, 15 h.",
    channels: [VOICE],
    room: "chambre de Jules",
    links: { ...s4, turn: "u-5" },
  });

  ev({
    ago: 120,
    type: "satellites.pairing_requested",
    kind: "satellite",
    title: "Le satellite esp32-cuisine (ESP32-S3 Box, pièce « cuisine ») demande l'appairage",
    detail: "Déclare : micro, haut-parleur",
    brand: "espressif",
    links: { satellite: "esp32-cuisine" },
  });

  // the school watch: voice fails (satellite offline), writing takes over
  const w2 = { watch: "w-2b77" };
  const trig2 = ev({
    ago: 96,
    type: "initiative.watch_triggered",
    kind: "watch",
    title: "Veille 2b77 déclenchée par « Sortie au musée vendredi »",
    detail: "L'école Jean-Moulin demande une autorisation signée avant jeudi.",
    brand: "gmail",
    links: { ...w2, connection: "c-gmail-mathis" },
  });
  ev({
    ago: 95.8,
    type: "initiative.watch_triaged",
    kind: "watch",
    title: "Tri : pertinent, à signaler aujourd'hui",
    detail: "Autorisation parentale à rendre avant jeudi.",
    links: w2,
    cause: trig2,
    record: { verdict: "relevant", urgent: true },
  });
  ev({
    ago: 95.6,
    type: "initiative.delivery_considered",
    kind: "delivery",
    title: "Décision de parler à Mathis — veille 2b77",
    reason: "Mathis est dans la pièce « bureau »",
    detail: "Prévu : à voix haute sur voice (bureau) puis par écrit sur telegram",
    people: ["mathis"],
    channels: [VOICE, "telegram"],
    room: "bureau",
    tone: "decision",
    links: { ...w2, delivery: "d-3" },
  });
  ev({
    ago: 95.5,
    type: "initiative.delivery_failed",
    kind: "delivery",
    title: "Message non transmis à voix haute — veille 2b77",
    detail: "Essayé : voice (bureau) — le satellite reachy-bureau ne répond plus.",
    people: ["mathis"],
    channels: [VOICE],
    room: "bureau",
    tone: "warning",
    links: { ...w2, delivery: "d-3", satellite: "reachy-bureau" },
  });
  ev({
    ago: 95.4,
    type: "initiative.delivered",
    kind: "delivery",
    title: "Message transmis par écrit — veille 2b77",
    detail: "« L'école demande l'autorisation pour la sortie de vendredi, avant jeudi. »",
    people: ["mathis"],
    channels: ["telegram"],
    links: { ...w2, delivery: "d-3" },
  });

  // a reminder Odile never received
  ev({
    ago: 80,
    type: "initiative.delivery_considered",
    kind: "delivery",
    title: "Décision d'écrire à Odile — rappel du déjeuner",
    reason: "aucune information de présence : retour à la conversation d'origine",
    detail: "Prévu : par écrit sur telegram",
    people: ["odile"],
    channels: ["telegram"],
    tone: "decision",
    links: { delivery: "d-4", session: "s-odile-0" },
  });
  ev({
    ago: 79.9,
    type: "initiative.delivery_failed",
    kind: "delivery",
    title: "Message non transmis — rappel du déjeuner",
    detail: "Telegram : le bot a été bloqué par la destinataire.",
    people: ["odile"],
    channels: ["telegram"],
    tone: "warning",
    links: { delivery: "d-4" },
  });

  // the kitchen light, with a slow model
  const s5 = { session: "s-lumiere" };
  const u6 = ev({
    ago: 61,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Mathis a dit",
    detail: "Richie, éteins la lumière de la cuisine.",
    people: ["mathis"],
    channels: [VOICE],
    room: "salon",
    links: { ...s5, turn: "u-6", satellite: "reachy-salon" },
  });
  ev({
    ago: 60.95,
    type: "conversation.fallback_spoken",
    kind: "conversation",
    title: "Réponse de secours : modèle trop lent",
    detail: "« Une seconde… »",
    channels: [VOICE],
    room: "salon",
    tone: "warning",
    links: { ...s5, turn: "u-6" },
    record: { reason: "model_slow", waited_ms: 2500 },
  });
  ev({
    ago: 60.9,
    type: "tools.tool_called",
    kind: "tool",
    title: "Outil ha_turn_off appelé",
    detail: '{"entity_id": "light.cuisine"}',
    tool: "ha_turn_off",
    brand: "home-assistant",
    people: ["mathis"],
    channels: [VOICE],
    links: { ...s5, turn: "u-6", call: "k-4", connection: "c-mcp-ha" },
    cause: u6,
  });
  ev({
    ago: 60.88,
    type: "tools.tool_completed",
    kind: "tool",
    title: "Outil ha_turn_off terminé en 0,4 s",
    detail: "light.cuisine : off",
    tool: "ha_turn_off",
    brand: "home-assistant",
    outcome: { ok: true, duration_s: 0.4 },
    links: { ...s5, turn: "u-6", call: "k-4", connection: "c-mcp-ha" },
  });
  ev({
    ago: 60.85,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "C'est éteint.",
    channels: [VOICE],
    room: "salon",
    links: { ...s5, turn: "u-6" },
  });

  // two tasks running right now
  const s6 = { session: "s-mutuelle" };
  const u7 = ev({
    ago: 31,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Mathis a dit",
    detail: "Prépare le dossier de remboursement de la mutuelle pour les lunettes de Jules.",
    people: ["mathis"],
    channels: ["telegram"],
    links: { ...s6, turn: "u-7" },
  });
  ev({
    ago: 30.9,
    type: "cognition.task_started",
    kind: "task",
    title: "Tâche 4410aa confiée à hermes",
    detail: "Préparer le dossier de remboursement des lunettes de Jules.",
    people: ["mathis"],
    channels: ["telegram"],
    brand: "hermes",
    links: { ...s6, turn: "u-7", task: "t-4410aa" },
    cause: u7,
  });
  ev({
    ago: 30.8,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "Je m'en occupe. Il me faudra la facture de l'opticien.",
    channels: ["telegram"],
    links: { ...s6, turn: "u-7" },
  });
  ev({
    ago: 18,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 4410aa : nouvelle étape",
    detail: "Formulaire de la mutuelle téléchargé.",
    brand: "hermes",
    links: { task: "t-4410aa" },
  });
  ev({
    ago: 9,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 4410aa : nouvelle étape",
    detail: "En attente de la facture : Gmail est à reconnecter.",
    brand: "hermes",
    links: { task: "t-4410aa" },
  });

  const s7 = { session: "s-courses" };
  const u8 = ev({
    ago: 12,
    type: "conversation.user_turn",
    kind: "conversation",
    title: "Léa a dit",
    detail: "Fais-moi la liste de courses de la semaine à partir de mes menus.",
    people: ["lea"],
    channels: ["web"],
    links: { ...s7, turn: "u-8" },
  });
  ev({
    ago: 11.9,
    type: "cognition.task_started",
    kind: "task",
    title: "Tâche 88b07e confiée à codex",
    detail: "Préparer la liste de courses de la semaine à partir des menus de Léa.",
    people: ["lea"],
    channels: ["web"],
    brand: "codex",
    links: { ...s7, turn: "u-8", task: "t-88b07e" },
    cause: u8,
  });
  ev({
    ago: 11.8,
    type: "conversation.assistant_turn",
    kind: "conversation",
    title: "Richie a répondu",
    detail: "Je prépare ça et je te l'envoie ici.",
    channels: ["web"],
    links: { ...s7, turn: "u-8" },
  });
  ev({
    ago: 6,
    type: "cognition.task_progressed",
    kind: "task",
    title: "Tâche 88b07e : nouvelle étape",
    detail: "Lecture du serveur MCP « Recettes de Léa ».",
    brand: "codex",
    links: { task: "t-88b07e" },
  });

  ev({
    ago: 4,
    type: "satellites.person_detected",
    kind: "observation",
    title: "2 personnes vues par reachy-salon (pièce « salon »)",
    detail: "Confiance : 87 %",
    room: "salon",
    links: { satellite: "reachy-salon" },
  });
  ev({
    ago: 2,
    type: "home.presence_changed",
    kind: "presence",
    title: "Jules est dans la pièce « salon »",
    people: ["jules"],
    room: "salon",
  });

  // positions, as the journal numbers its entries: oldest first, causes pointing at positions
  events.sort((a, b) => (a.at < b.at ? -1 : 1));
  const position = new Map(events.map((e, i) => [e.uid, String(i + 1)]));
  for (const e of events) {
    e.id = position.get(e.uid) ?? e.id;
    e.cause = e.cause ? (position.get(e.cause) ?? null) : null;
  }
  return events.reverse();
}

/** What the live stream brings, in turn, while `pnpm dev` runs. */
export const LIVE: Omit<JournalItem, "id" | "at" | "uid" | "kind_label">[] = ([] as LiveDraft[])
  .concat([
    {
      type: "cognition.task_progressed",
      kind: "task",
      title: "Tâche 88b07e : nouvelle étape",
      detail: "Liste regroupée par rayon : 34 articles.",
      people: [],
      channels: [],
      room: null,
      tone: "normal",
      links: { task: "t-88b07e" },
      cause: null,
      outcome: null,
      tool: null,
      brand: "codex",
    },
    {
      type: "satellites.speech_activity",
      kind: "observation",
      title: "Parole détectée près de reachy-salon (pièce « salon »)",
      detail: "",
      people: [],
      channels: [],
      room: "salon",
      tone: "normal",
      links: { satellite: "reachy-salon" },
      cause: null,
      outcome: null,
      tool: null,
      brand: null,
    },
    {
      type: "conversation.user_turn",
      kind: "conversation",
      title: "Jules a dit",
      detail: "Richie, tu peux mettre de la musique ?",
      people: ["jules"],
      channels: ["voice"],
      room: "salon",
      tone: "normal",
      links: { session: "s-live", turn: "u-live" },
      cause: null,
      outcome: null,
      tool: null,
      brand: "voice",
    },
    {
      type: "conversation.assistant_turn",
      kind: "conversation",
      title: "Richie a répondu",
      detail: "Je lance ta playlist du mercredi.",
      people: [],
      channels: ["voice"],
      room: "salon",
      tone: "normal",
      links: { session: "s-live", turn: "u-live" },
      cause: null,
      outcome: null,
      tool: null,
      brand: "voice",
    },
  ])
  .map(toItem);
