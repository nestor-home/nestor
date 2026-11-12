/**
 * A day of Richie at the Lambert's, as the journal records it: linked events that the admin turns
 * into threads (a conversation and its tool calls) and chains (a watch triggered → announced →
 * followed up; a task started → progressing → delivered). Times are minutes before "now". Written
 * in English, the French of each text beside it (`fr`).
 */
import type { JournalEvent, JournalItem } from "@/api";
import {
  BEDROOM,
  CLAIM,
  CLAIM_STEPS,
  ENERGY,
  ENERGY_RESULT,
  ENERGY_STEPS,
  GYM_ERROR,
  HANDBALL,
  KITCHEN,
  LIVING_ROOM,
  OFFICE,
  ref,
  SHOPPING,
  SHOPPING_STEP,
} from "./fixtures";
import { fr } from "./french";
import { type Draft as ItemDraft, toItem } from "./messages";

interface Draft extends ItemDraft {
  ago: number; // minutes before now
  cause?: string | null; // the id of the event that led to this one
  record?: Record<string, unknown>;
}

const VOICE = "voice";

/** A voice message, transcribed: its words are also the turn's. */
const voiceNote = (transcript: string): JournalItem["attachments"][number] => ({
  index: 0,
  kind: "voice",
  media_type: "audio/ogg",
  size: 21_300,
  name: null,
  transcript,
});

export function day(now = Date.now()): JournalEvent[] {
  let seq = 0;
  const events: JournalEvent[] = [];
  const causes = new Map<string, string>(); // event id → the id of its cause
  const at = (ago: number) => new Date(now - ago * 60_000).toISOString();

  function ev({ ago, cause, record, ...draft }: Draft): string {
    const id = `e-${String(++seq).padStart(4, "0")}`;
    const item = toItem(
      { ...draft, reason: draft.reason && draft.reason !== "model_slow" ? draft.reason : undefined },
      { position: 0, id, at: at(ago) },
    );
    if (cause) causes.set(id, cause);
    events.push({
      item,
      record: {
        type: draft.type,
        version: 1,
        at: item.at,
        ...(record ?? {}),
        ...Object.fromEntries(Object.entries(draft.links ?? {}).map(([k, v]) => [`${k}_id`, v])),
      },
    });
    return id;
  }

  // -- earlier days: a quieter background, single events ------------------------------------------
  const odileSaid = fr(
    "Hello Richie, remind Léa I'm coming on Sunday.",
    "Bonjour Richie, rappelle à Léa que je viens dimanche.",
  );
  const BACKGROUND: Omit<Draft, "ago">[] = [
    {
      type: "presence.changed",
      title: `Mathis is in the ${KITCHEN}`,
      people: [ref("mathis")],
      room: KITCHEN,
      record: { person: "mathis", home: true, room: KITCHEN },
    },
    {
      type: "observation.person.detected",
      title: `1 person seen by reachy-living-room (room “${LIVING_ROOM}”)`,
      detail: fr("Confidence: 91%", "Confiance : 91 %"),
      room: LIVING_ROOM,
      links: { satellite: "reachy-living-room" },
      record: { count: 1, confidence: 0.91 },
    },
    {
      type: "conversation.turn.user",
      title: "Odile said",
      detail: odileSaid,
      people: [ref("odile")],
      channels: ["telegram"],
      links: { session: "s-odile" },
      attachments: [voiceNote(odileSaid)],
      record: { text: odileSaid },
    },
    {
      type: "conversation.turn.assistant",
      title: "Richie answered",
      detail: fr("Got it, I'll tell her tonight.", "Bien reçu, je lui dirai ce soir."),
      channels: ["telegram"],
      links: { session: "s-odile" },
    },
    {
      type: "observation.speech.activity",
      title: `Speech detected near reachy-office (room “${OFFICE}”)`,
      room: OFFICE,
      links: { satellite: "reachy-office" },
    },
    {
      type: "presence.changed",
      title: `Jules is in the ${BEDROOM}`,
      people: [ref("jules")],
      room: BEDROOM,
    },
    {
      type: "agent.tool.called",
      title: "Tool ha_get_state called",
      detail: '{"entity_id": "sensor.living_room_temperature"}',
      tool: "ha_get_state",
      brand: "home-assistant",
      links: { call: "c-bg", connection: "c-mcp-ha" },
    },
    {
      type: "agent.tool.completed",
      title: "Tool ha_get_state finished in 0.3 s",
      detail: fr("19.5 °C", "19,5 °C"),
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
    type: "conversation.turn.user",
    title: "Léa said",
    detail: fr(
      "Tell me as soon as the school replies about the trip.",
      "Dis-moi dès que l'école répond pour la sortie.",
    ),
    people: [ref("lea")],
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier" },
  });
  ev({
    ago: 60 * 28 - 0.2,
    type: "watch.created",
    title: `Watch created: ${fr("news from the school for Léa", "les nouvelles de l'école pour Léa")}`,
    people: [ref("lea")],
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier", watch: "w-9d41" },
    cause: born,
  });
  ev({
    ago: 60 * 28 - 0.3,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr(
      "I'm watching your inbox: I'll tell you as soon as they reply.",
      "Je surveille ta boîte : je te préviens dès qu'ils répondent.",
    ),
    channels: ["telegram"],
    links: { session: "s-hier", turn: "t-hier" },
  });
  ev({
    ago: 60 * 26 - 9,
    type: "task.ended",
    title: "Task a04f12 failed (9 min)",
    detail: GYM_ERROR,
    tone: "warning",
    brand: "hermes",
    outcome: { ok: false, duration_s: 540 },
    links: { task: "t-a04f12" },
  });

  // -- this morning -------------------------------------------------------------------------------
  ev({
    ago: 412,
    type: "presence.changed",
    title: `Mathis is in the ${KITCHEN}`,
    people: [ref("mathis")],
    room: KITCHEN,
    record: { person: "mathis", home: true, room: KITCHEN },
  });
  ev({
    ago: 405,
    type: "presence.changed",
    title: `Léa is in the ${LIVING_ROOM}`,
    people: [ref("lea")],
    room: LIVING_ROOM,
  });

  // a voice exchange in the living room, with a tool call
  const s1 = { session: "s-matin" };
  const today = fr("Richie, what do I have today?", "Richie, qu'est-ce que j'ai aujourd'hui ?");
  const u1 = ev({
    ago: 398,
    type: "conversation.turn.user",
    title: "Léa said",
    detail: today,
    people: [ref("lea")],
    channels: [VOICE],
    room: LIVING_ROOM,
    links: { ...s1, turn: "u-1", satellite: "reachy-living-room" },
    record: { text: today, speaker: "lea", speaker_confidence: 0.88 },
  });
  ev({
    ago: 397.9,
    type: "agent.tool.called",
    title: "Tool calendar_list called",
    detail: '{"day": "today", "calendar": "lea"}',
    tool: "calendar_list",
    brand: "google-calendar",
    people: [ref("lea")],
    channels: [VOICE],
    links: { ...s1, turn: "u-1", call: "k-1" },
    cause: u1,
  });
  ev({
    ago: 397.8,
    type: "agent.tool.completed",
    title: "Tool calendar_list finished in 0.7 s",
    detail: fr("2 events: “Team meeting” 10:00, “Yoga” 19:00", "2 événements : « Point équipe » 10:00, « Yoga » 19:00"),
    tool: "calendar_list",
    brand: "google-calendar",
    outcome: { ok: true, duration_s: 0.7 },
    links: { ...s1, turn: "u-1", call: "k-1" },
  });
  ev({
    ago: 397.7,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr(
      "A team meeting at 10, then your yoga at 7 pm. Nothing else.",
      "Un point d'équipe à 10 h, puis ton yoga à 19 h. Rien d'autre.",
    ),
    channels: [VOICE],
    room: LIVING_ROOM,
    links: { ...s1, turn: "u-1" },
    record: { latency_ms: 1180, model: "claude-sonnet-4.6" },
  });

  // Mathis asks on Telegram for a long task: a thread and a chain at once
  const s2 = { session: "s-elec" };
  const u2 = ev({
    ago: 352,
    type: "conversation.turn.user",
    title: "Mathis said",
    detail: fr(
      "Can you compare the green electricity offers? Go by my last bills.",
      "Tu peux comparer les offres d'électricité verte ? Base-toi sur mes dernières factures.",
    ),
    people: [ref("mathis")],
    channels: ["telegram"],
    links: { ...s2, turn: "u-2" },
    attachments: [
      { index: 0, kind: "image", media_type: "image/png", size: 668, name: null, transcript: null },
      {
        index: 1,
        kind: "file",
        media_type: "application/pdf",
        size: 182_400,
        name: fr("bill-october.pdf", "facture-octobre.pdf"),
        transcript: null,
      },
    ],
  });
  ev({
    ago: 351.9,
    type: "agent.tool.called",
    title: "Tool mail_search called",
    detail: '{"query": "electricity bill", "limit": 2}',
    tool: "mail_search",
    brand: "gmail",
    people: [ref("mathis")],
    channels: ["telegram"],
    links: { ...s2, turn: "u-2", call: "k-2", connection: "c-gmail-mathis" },
    cause: u2,
  });
  ev({
    ago: 351.8,
    type: "agent.tool.completed",
    title: "Tool mail_search finished in 0.8 s",
    detail: fr(
      "2 emails: “Your September bill”, “Your August bill”.",
      "2 courriels : « Votre facture de septembre », « Votre facture d'août ».",
    ),
    tool: "mail_search",
    brand: "gmail",
    outcome: { ok: true, duration_s: 0.8 },
    links: { ...s2, turn: "u-2", call: "k-2", connection: "c-gmail-mathis" },
  });
  const started = ev({
    ago: 351.6,
    type: "task.started",
    title: "Task 3f2a1c handed to hermes",
    detail: ENERGY,
    people: [ref("mathis")],
    channels: ["telegram"],
    brand: "hermes",
    links: { ...s2, turn: "u-2", task: "t-3f2a1c" },
    cause: u2,
  });
  ev({
    ago: 351.5,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr(
      "On it: I'll let you know as soon as I have the figures.",
      "C'est parti : je te préviens dès que j'ai les chiffres.",
    ),
    channels: ["telegram"],
    links: { ...s2, turn: "u-2" },
  });
  ev({
    ago: 340,
    type: "task.progress",
    title: "Task 3f2a1c: new step",
    detail: ENERGY_STEPS[0],
    brand: "hermes",
    links: { task: "t-3f2a1c" },
    cause: started,
  });
  ev({
    ago: 318,
    type: "task.progress",
    title: "Task 3f2a1c: new step",
    detail: ENERGY_STEPS[1],
    brand: "hermes",
    links: { task: "t-3f2a1c" },
  });
  ev({
    ago: 290,
    type: "task.progress",
    title: "Task 3f2a1c: new step",
    detail: ENERGY_STEPS[2],
    brand: "hermes",
    links: { task: "t-3f2a1c" },
  });
  const ended = ev({
    ago: 251,
    type: "task.ended",
    title: "Task 3f2a1c completed (1 h 41)",
    detail: ENERGY_RESULT,
    brand: "hermes",
    outcome: { ok: true, duration_s: 6060 },
    links: { task: "t-3f2a1c" },
  });
  ev({
    ago: 250.6,
    type: "initiative.considered",
    title: "Decided to speak to Mathis: task 3f2a1c completed",
    reason: `Mathis is in the ${OFFICE}`,
    detail: fr("Planned: aloud on voice (office)", "Prévu : à voix haute sur voice (bureau)"),
    people: [ref("mathis")],
    channels: [VOICE],
    room: OFFICE,
    tone: "decision",
    links: { task: "t-3f2a1c", delivery: "d-1" },
    cause: ended,
    record: { policy: "presence", spoken: "voice:office", written: null },
  });
  ev({
    ago: 250.4,
    type: "initiative.delivered",
    title: "Message passed on: task 3f2a1c",
    detail: fr(
      "“Mathis, I've finished the comparison: the second offer is the cheapest.”",
      "« Mathis, j'ai fini la comparaison : la deuxième offre est la moins chère. »",
    ),
    people: [ref("mathis")],
    channels: [VOICE],
    room: OFFICE,
    links: { task: "t-3f2a1c", delivery: "d-1", satellite: "reachy-office" },
  });

  // the school: a watch triggered, announced by voice, then followed up in writing
  const w = { watch: "w-9d41" };
  const confirmed = fr("Friday's trip confirmed", "Sortie de vendredi confirmée");
  const trig = ev({
    ago: 230,
    type: "watch.triggered",
    title: `Watch 9d41 triggered by “${confirmed}”`,
    detail: fr(
      "The school confirms Friday's trip; pack a picnic.",
      "L'école confirme la sortie de vendredi ; prévoir un pique-nique.",
    ),
    people: [ref("lea")],
    brand: "imap",
    links: { ...w, connection: "c-imap-lea" },
    record: { item: { kind: "mail", from: "office@school.example", subject: confirmed } },
  });
  ev({
    ago: 229.6,
    type: "initiative.considered",
    title: "Decided to speak to Léa: watch 9d41",
    reason: `Léa is in the ${LIVING_ROOM}`,
    cause: trig,
    detail: fr("Planned: aloud on voice (living room)", "Prévu : à voix haute sur voice (salon)"),
    people: [ref("lea")],
    channels: [VOICE],
    room: LIVING_ROOM,
    tone: "decision",
    links: { ...w, delivery: "d-2" },
  });
  ev({
    ago: 229.4,
    type: "initiative.delivered",
    title: "Message passed on: watch 9d41",
    detail: fr(
      "“Léa, the school has replied: Friday's trip is on.”",
      "« Léa, l'école a répondu : la sortie de vendredi est maintenue. »",
    ),
    people: [ref("lea")],
    channels: [VOICE],
    room: LIVING_ROOM,
    links: { ...w, delivery: "d-2", satellite: "reachy-living-room" },
  });
  ev({
    ago: 205,
    type: "presence.changed",
    title: "Léa is no longer home",
    people: [ref("lea")],
  });
  ev({
    ago: 199.4,
    type: "initiative.delivered",
    title: "Message passed on: watch 9d41 (follow-up)",
    detail: fr(
      "“The school confirms Friday's trip. Remember the picnic.”",
      "« L'école confirme la sortie de vendredi. Pense au pique-nique. »",
    ),
    people: [ref("lea")],
    channels: ["telegram"],
    links: { ...w, delivery: "d-2" },
  });
  const s3 = { session: "s-ecole" };
  ev({
    ago: 190,
    type: "conversation.turn.user",
    title: "Léa said",
    detail: fr("Thanks! Put it in the family calendar.", "Merci ! Mets-la dans l'agenda de la famille."),
    people: [ref("lea")],
    channels: ["telegram"],
    links: { ...s3, turn: "u-3", watch: "w-9d41" },
  });
  ev({
    ago: 189.9,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr("Done: Friday, for the whole house.", "C'est fait : vendredi, pour toute la maison."),
    channels: ["telegram"],
    links: { ...s3, turn: "u-3" },
  });

  // Gmail stops answering: a failed tool call, then the connection needs a reconnect
  ev({
    ago: 171,
    type: "agent.tool.called",
    title: "Tool mail_search called",
    detail: '{"query": "glasses invoice", "limit": 5}',
    tool: "mail_search",
    brand: "gmail",
    people: [ref("mathis")],
    links: { call: "k-3", connection: "c-gmail-mathis", task: "t-4410aa" },
  });
  const failed = ev({
    ago: 170.9,
    type: "agent.tool.completed",
    title: "Tool mail_search failed",
    detail: fr("Google refused the access token (invalid_grant).", "Google a refusé le jeton d'accès (invalid_grant)."),
    tool: "mail_search",
    brand: "gmail",
    tone: "warning",
    outcome: { ok: false, duration_s: 1.2 },
    links: { call: "k-3", connection: "c-gmail-mathis", task: "t-4410aa" },
  });
  ev({
    ago: 170.8,
    type: "connection.changed",
    title: "Connection mathis.lambert27@gmail.com needs to be authorised again",
    detail: fr(
      "Google refused to renew the token: reconnect the account.",
      "Google a refusé le renouvellement du jeton : reconnectez le compte.",
    ),
    people: [ref("mathis")],
    brand: "gmail",
    tone: "warning",
    links: { connection: "c-gmail-mathis" },
    cause: failed,
  });

  // Jules interrupts, then teaches Richie something
  const s4 = { session: "s-jules" };
  ev({
    ago: 150,
    type: "conversation.turn.user",
    title: "Jules said",
    detail: fr("Richie, when is my handball practice?", "Richie, c'est quand mon entraînement de hand ?"),
    people: [ref("jules")],
    channels: [VOICE],
    room: BEDROOM,
    links: { ...s4, turn: "u-4", satellite: "pi-bedroom" },
  });
  ev({
    ago: 149.9,
    type: "conversation.turn.assistant",
    title: "Richie answered (interrupted)",
    detail: fr(
      "Wednesday at 2 pm, as every week. Don't forget your water bottle and…",
      "Mercredi à 14 h, comme chaque semaine. N'oublie pas ta gourde et…",
    ),
    channels: [VOICE],
    room: BEDROOM,
    links: { ...s4, turn: "u-4" },
    record: { interrupted: true },
  });
  ev({
    ago: 149.85,
    type: "conversation.turn.cut",
    title: "Answer cut off by the person",
    detail: fr("Heard: “stop, that's fine”", "Entendu : « stop, c'est bon »"),
    people: [ref("jules")],
    channels: [VOICE],
    room: BEDROOM,
    links: { ...s4, turn: "u-4" },
  });
  const u5 = ev({
    ago: 149.5,
    type: "conversation.turn.user",
    title: "Jules said",
    detail: fr("And can you remember it's at 3 pm now?", "Et tu peux retenir que maintenant c'est à 15 h ?"),
    people: [ref("jules")],
    channels: [VOICE],
    room: BEDROOM,
    links: { ...s4, turn: "u-5" },
  });
  ev({
    ago: 149.4,
    type: "memory.recorded",
    title: "Memory recorded",
    detail: HANDBALL,
    people: [ref("jules")],
    channels: [VOICE],
    links: { ...s4, turn: "u-5", memory: "m-07" },
    cause: u5,
  });
  ev({
    ago: 149.3,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr("Noted: Wednesday, 3 pm.", "C'est noté : mercredi, 15 h."),
    channels: [VOICE],
    room: BEDROOM,
    links: { ...s4, turn: "u-5" },
  });

  ev({
    ago: 120,
    type: "satellite.pairing.requested",
    title: `Satellite esp32-kitchen (ESP32-S3 Box, room “${KITCHEN}”) asks to pair`,
    detail: fr("Declares: microphone, speaker", "Déclare : micro, haut-parleur"),
    brand: "espressif",
    links: { satellite: "esp32-kitchen" },
  });

  // the school watch: voice fails (satellite offline), writing takes over
  const w2 = { watch: "w-2b77" };
  const trig2 = ev({
    ago: 96,
    type: "watch.triggered",
    title: `Watch 2b77 triggered by “${fr("Museum trip on Friday", "Sortie au musée vendredi")}”`,
    detail: fr(
      "Jean-Moulin school asks for a signed permission slip before Thursday.",
      "L'école Jean-Moulin demande une autorisation signée avant jeudi.",
    ),
    brand: "gmail",
    links: { ...w2, connection: "c-gmail-mathis" },
  });
  ev({
    ago: 95.6,
    type: "initiative.considered",
    title: "Decided to speak to Mathis: watch 2b77",
    reason: `Mathis is in the ${OFFICE}`,
    cause: trig2,
    detail: fr(
      "Planned: aloud on voice (office), then in writing on telegram",
      "Prévu : à voix haute sur voice (bureau) puis par écrit sur telegram",
    ),
    people: [ref("mathis")],
    channels: [VOICE, "telegram"],
    room: OFFICE,
    tone: "decision",
    links: { ...w2, delivery: "d-3" },
  });
  ev({
    ago: 95.5,
    type: "initiative.undeliverable",
    title: "Message not passed on: watch 2b77",
    detail: fr(
      "Tried: voice (office). Satellite reachy-office no longer answers.",
      "Essayé : voice (bureau). Le satellite reachy-office ne répond plus.",
    ),
    people: [ref("mathis")],
    channels: [VOICE],
    room: OFFICE,
    tone: "warning",
    links: { ...w2, delivery: "d-3", satellite: "reachy-office" },
  });
  ev({
    ago: 95.4,
    type: "initiative.delivered",
    title: "Message passed on: watch 2b77",
    detail: fr(
      "“The school wants the permission slip for Friday's trip by Thursday.”",
      "« L'école demande l'autorisation pour la sortie de vendredi, avant jeudi. »",
    ),
    people: [ref("mathis")],
    channels: ["telegram"],
    links: { ...w2, delivery: "d-3" },
  });

  // the TV's price, checked: still above the threshold, so nothing to tell
  ev({
    ago: 85,
    type: "initiative.considered",
    title: "Decided to speak to Mathis: schedule sc-tv",
    reason: "Mathis is away",
    detail: fr("Planned: in writing on telegram", "Prévu : par écrit sur telegram"),
    people: [ref("mathis")],
    channels: ["telegram"],
    tone: "decision",
    links: { delivery: "schedule:sc-tv" },
  });
  ev({
    ago: 84.8,
    type: "initiative.withheld",
    title: "Nothing to tell: schedule sc-tv",
    people: [ref("mathis")],
    channels: ["telegram"],
    links: { delivery: "schedule:sc-tv" },
  });

  // a reminder Odile never received
  ev({
    ago: 80,
    type: "initiative.considered",
    title: "Decided to speak to Odile: schedule sc-lunch",
    reason: "no presence information: back to the conversation it came from",
    detail: fr("Planned: in writing on telegram", "Prévu : par écrit sur telegram"),
    people: [ref("odile")],
    channels: ["telegram"],
    tone: "decision",
    links: { delivery: "d-4", session: "s-odile-0" },
  });
  ev({
    ago: 79.9,
    type: "initiative.undeliverable",
    title: "Message not passed on: schedule sc-lunch",
    detail: fr("Telegram: the recipient has blocked the bot.", "Telegram : le bot a été bloqué par la destinataire."),
    people: [ref("odile")],
    channels: ["telegram"],
    tone: "warning",
    links: { delivery: "d-4" },
  });

  // the kitchen light, with a slow model
  const s5 = { session: "s-lumiere" };
  const u6 = ev({
    ago: 61,
    type: "conversation.turn.user",
    title: "Mathis said",
    detail: fr("Richie, turn off the kitchen light.", "Richie, éteins la lumière de la cuisine."),
    people: [ref("mathis")],
    channels: [VOICE],
    room: LIVING_ROOM,
    links: { ...s5, turn: "u-6", satellite: "reachy-living-room" },
  });
  ev({
    ago: 60.95,
    type: "conversation.fallback",
    title: "Fallback answer: model too slow",
    detail: fr("“One second…”", "« Une seconde… »"),
    channels: [VOICE],
    room: LIVING_ROOM,
    tone: "warning",
    links: { ...s5, turn: "u-6" },
    record: { reason: "model_slow", waited_ms: 2500 },
  });
  ev({
    ago: 60.9,
    type: "agent.tool.called",
    title: "Tool ha_turn_off called",
    detail: '{"entity_id": "light.kitchen"}',
    tool: "ha_turn_off",
    brand: "home-assistant",
    people: [ref("mathis")],
    channels: [VOICE],
    links: { ...s5, turn: "u-6", call: "k-4", connection: "c-mcp-ha" },
    cause: u6,
  });
  ev({
    ago: 60.88,
    type: "agent.tool.completed",
    title: "Tool ha_turn_off finished in 0.4 s",
    detail: fr("light.kitchen: off", "light.kitchen : off"),
    tool: "ha_turn_off",
    brand: "home-assistant",
    outcome: { ok: true, duration_s: 0.4 },
    links: { ...s5, turn: "u-6", call: "k-4", connection: "c-mcp-ha" },
  });
  ev({
    ago: 60.85,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr("It's off.", "C'est éteint."),
    channels: [VOICE],
    room: LIVING_ROOM,
    links: { ...s5, turn: "u-6" },
  });

  // two tasks running right now
  const s6 = { session: "s-mutuelle" };
  const u7 = ev({
    ago: 31,
    type: "conversation.turn.user",
    title: "Mathis said",
    detail: fr(
      "Prepare the health insurance claim for Jules's glasses.",
      "Prépare le dossier de remboursement de la mutuelle pour les lunettes de Jules.",
    ),
    people: [ref("mathis")],
    channels: ["telegram"],
    links: { ...s6, turn: "u-7" },
  });
  ev({
    ago: 30.9,
    type: "task.started",
    title: "Task 4410aa handed to hermes",
    detail: CLAIM,
    people: [ref("mathis")],
    channels: ["telegram"],
    brand: "hermes",
    links: { ...s6, turn: "u-7", task: "t-4410aa" },
    cause: u7,
  });
  ev({
    ago: 30.8,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr(
      "I'm on it. I'll need the optician's invoice.",
      "Je m'en occupe. Il me faudra la facture de l'opticien.",
    ),
    channels: ["telegram"],
    links: { ...s6, turn: "u-7" },
  });
  ev({
    ago: 18,
    type: "task.progress",
    title: "Task 4410aa: new step",
    detail: CLAIM_STEPS[0],
    brand: "hermes",
    links: { task: "t-4410aa" },
  });
  ev({
    ago: 9,
    type: "task.progress",
    title: "Task 4410aa: new step",
    detail: CLAIM_STEPS[1],
    brand: "hermes",
    links: { task: "t-4410aa" },
  });

  const s7 = { session: "s-courses" };
  const u8 = ev({
    ago: 12,
    type: "conversation.turn.user",
    title: "Léa said",
    detail: fr(
      "Make me the week's shopping list from my menus.",
      "Fais-moi la liste de courses de la semaine à partir de mes menus.",
    ),
    people: [ref("lea")],
    channels: ["web"],
    links: { ...s7, turn: "u-8" },
  });
  ev({
    ago: 11.9,
    type: "task.started",
    title: "Task 88b07e handed to codex",
    detail: SHOPPING,
    people: [ref("lea")],
    channels: ["web"],
    brand: "codex",
    links: { ...s7, turn: "u-8", task: "t-88b07e" },
    cause: u8,
  });
  ev({
    ago: 11.8,
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr("I'll put it together and send it to you here.", "Je prépare ça et je te l'envoie ici."),
    channels: ["web"],
    links: { ...s7, turn: "u-8" },
  });
  ev({
    ago: 6,
    type: "task.progress",
    title: "Task 88b07e: new step",
    detail: SHOPPING_STEP,
    brand: "codex",
    links: { task: "t-88b07e" },
  });

  ev({
    ago: 4,
    type: "observation.person.detected",
    title: `2 people seen by reachy-living-room (room “${LIVING_ROOM}”)`,
    detail: fr("Confidence: 87%", "Confiance : 87 %"),
    room: LIVING_ROOM,
    links: { satellite: "reachy-living-room" },
  });
  ev({
    ago: 2,
    type: "presence.changed",
    title: `Jules is in the ${LIVING_ROOM}`,
    people: [ref("jules")],
    room: LIVING_ROOM,
  });

  // positions, as the journal numbers its entries: oldest first, causes pointing at positions
  events.sort((a, b) => (a.item.at < b.item.at ? -1 : 1));
  // as the server stamps them: each session's talk is one conversation (Assist's model), and every
  // event of a turn (the message, its tool calls, memories, tasks, the reply) carries the turn's id
  const turnOf = new Map<string, string>();
  for (const { item } of events) {
    const session = item.links.session;
    if (!session) continue;
    item.links.conversation = `conv-${session}`;
    if (item.message.id === "journal-user-said") turnOf.set(session, item.links.turn ?? `turn-${item.id}`);
    item.links.turn = item.links.turn ?? turnOf.get(session) ?? null;
  }
  const position = new Map(events.map((e, i) => [e.item.id, i + 1]));
  for (const { item } of events) {
    item.position = position.get(item.id) ?? 0;
    const cause = causes.get(item.id);
    item.cause = cause ? (position.get(cause) ?? null) : null;
  }
  return events.reverse();
}

/** What the live stream brings, in turn, while `pnpm dev` runs. */
export const LIVE: ItemDraft[] = [
  {
    type: "task.progress",
    title: "Task 88b07e: new step",
    detail: fr("List grouped by aisle: 34 items.", "Liste regroupée par rayon : 34 articles."),
    links: { task: "t-88b07e" },
    brand: "codex",
  },
  {
    type: "observation.speech.activity",
    title: `Speech detected near reachy-living-room (room “${LIVING_ROOM}”)`,
    room: LIVING_ROOM,
    links: { satellite: "reachy-living-room" },
    brand: null,
  },
  {
    type: "conversation.turn.user",
    title: "Jules said",
    detail: fr("Richie, can you put some music on?", "Richie, tu peux mettre de la musique ?"),
    people: [ref("jules")],
    channels: ["voice"],
    room: LIVING_ROOM,
    links: { session: "s-live", turn: "u-live" },
    brand: "voice",
  },
  {
    type: "conversation.turn.assistant",
    title: "Richie answered",
    detail: fr("Playing your Wednesday playlist.", "Je lance ta playlist du mercredi."),
    channels: ["voice"],
    room: LIVING_ROOM,
    links: { session: "s-live", turn: "u-live" },
    brand: "voice",
  },
];
