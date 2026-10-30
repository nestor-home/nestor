/**
 * The mock server's English for the static texts it owns (connector guides, tool descriptions,
 * capability labels, health details). The real server renders these from its catalogue; here a
 * table is enough. Content people wrote (tasks, watches, memories) is never translated.
 */
const EN: Record<string, string> = {
  "Boîte mail (IMAP)": "Mailbox (IMAP)",
  "Google Agenda": "Google Calendar",
  "Serveur MCP": "MCP server",
  "Lire, chercher et rédiger des courriels ; surveiller ce qui arrive dans la boîte.":
    "Read, search and draft emails; watch what arrives in the inbox.",
  "N'importe quelle boîte mail par IMAP : Fastmail, Proton Bridge, Orange, OVH…":
    "Any mailbox over IMAP: Fastmail, Proton Bridge, Orange, OVH…",
  "Les outils d'un serveur Model Context Protocol, local ou distant : Home Assistant, vos scripts…":
    "The tools of a Model Context Protocol server, local or remote: Home Assistant, your scripts…",
  "Consulter les agendas du foyer et y ajouter des événements.": "Read the household's calendars and add events.",
  "Utilisez un mot de passe d'application plutôt que votre mot de passe principal quand le fournisseur le propose.":
    "Use an app password rather than your main password when the provider offers one.",
  "Indiquez l'adresse HTTP du serveur (transport « streamable HTTP »). Le jeton est facultatif.":
    "Give the server's HTTP address (“streamable HTTP” transport). The token is optional.",
  "Serveur IMAP": "IMAP server",
  Identifiant: "Username",
  "Mot de passe d'application": "App password",
  "Nom affiché": "Display name",
  "Adresse du serveur": "Server address",
  "Jeton d'accès": "Access token",
  "Notes de cuisine": "Kitchen notes",
  "Google a refusé le renouvellement du jeton (invalid_grant).": "Google refused to renew the token (invalid_grant).",
  "Connexion refusée par http://192.168.1.20:8808/mcp.": "Connection refused by http://192.168.1.20:8808/mcp.",
  "Chercher des courriels par expéditeur, sujet ou date.": "Search emails by sender, subject or date.",
  "Lire un courriel et ses pièces jointes texte.": "Read an email and its text attachments.",
  "Préparer un brouillon de réponse, sans l'envoyer.": "Draft a reply without sending it.",
  "Classer un courriel (libellés, archivage).": "File an email (labels, archive).",
  "Envoyer un courriel au nom de la personne.": "Send an email on the person's behalf.",
  "Lire l'état d'un appareil ou d'un capteur.": "Read the state of a device or sensor.",
  "Lister les pièces et leurs appareils.": "List the rooms and their devices.",
  "Allumer une lumière, une prise ou une scène.": "Turn on a light, a plug or a scene.",
  "Éteindre une lumière, une prise ou une scène.": "Turn off a light, a plug or a scene.",
  "Déverrouiller une serrure connectée.": "Unlock a smart lock.",
  micro: "microphone",
  "haut-parleur": "speaker",
  "détection de parole": "speech detection",
  "détection de personnes (sans image transmise)": "person detection (no image sent)",
  expressions: "expressions",
  "mouvements de tête": "head movements",
  "Claude Haiku 4.5 (tri des veilles)": "Claude Haiku 4.5 (watch triage)",
  "Reconnaissance vocale": "Speech recognition",
  "Synthèse vocale": "Speech synthesis",
  "Détection de parole": "Speech detection",
  "Fin de tour": "End of turn",
  "Voix (satellites)": "Voice (satellites)",
  "Client vocal du navigateur": "Browser voice client",
  "Présence par Home Assistant": "Presence from Home Assistant",
  "Maison (MCP de Home Assistant)": "Home (Home Assistant MCP)",
  "Recettes de Léa (MCP)": "Léa's recipes (MCP)",
  "Journal et état": "Journal and state",
  Réplication: "Replication",
  Conteneur: "Container",
  "Chat web": "Web chat",
  "Dans l'administration et sur le réseau du foyer": "In the admin and on the household network",
  "Premier jeton en 640 ms (médiane du jour)": "First token in 640 ms (today's median)",
  "Latence élevée depuis 13:40 (p95 1,9 s)": "High latency since 13:40 (p95 1.9 s)",
  "1 tâche en cours": "1 task running",
  "2 satellites connectés sur 3": "2 of 3 satellites connected",
  "Pour le développement": "For development",
  "4 personnes suivies": "4 people tracked",
  "5 outils": "5 tools",
  "Connexion refusée par 192.168.1.20:8808": "Connection refused by 192.168.1.20:8808",
  "1 compte à réautoriser": "1 account to reauthorise",
  "Hors ligne depuis 97 min": "Offline for 97 min",
  "212 Mo, 48 112 événements": "212 MB, 48,112 events",
  "Dernière réplique il y a 12 s": "Last replica 12 s ago",
  Conversations: "Conversations",
  "Prises de parole": "Speaking up",
  Outils: "Tools",
  Tâches: "Tasks",
  Veilles: "Watches",
  Souvenirs: "Memories",
  Connexions: "Connections",
  Présence: "Presence",
  Observations: "Observations",
};

const SETUP_EN = `1. Open the Google Cloud console and create a project for the household.
2. Enable the API (APIs & Services › Library).
3. Under “OAuth consent screen”, choose “External” and add your addresses as test users.
4. Create “OAuth client ID” credentials, type “Web application”.
5. Declare the redirect URI below, then copy the client ID and secret.`;

function translate(text: string): string {
  if (text.startsWith("1. Ouvrez la console Google Cloud")) return SETUP_EN;
  return EN[text] ?? text;
}

/** A response body as the server sends it to an English reader: every static text translated. */
export function inEnglish<T>(value: T): T {
  if (typeof value === "string") return translate(value) as T;
  if (Array.isArray(value)) return value.map(inEnglish) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, inEnglish(v)])) as T;
  }
  return value;
}
