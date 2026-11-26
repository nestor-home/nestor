/**
 * The one instance every screen of the mock describes: Richie, serving the Martin household. Its configuration
 * file is the source of what exists (models, channels, executors, tools, inbound sources, the home, connectors,
 * the people and where they are written to); what runs, who is reached where and what an alert can wait for are
 * read from it here, never typed again. What the file cannot know (health, versions, presence) is in `fixtures`.
 */
import type { Component, ConfigDocument, ModelType } from "@/api";
import type { components } from "@/api/schema.gen";
import { isRecord, type Slot } from "@/features/config/schema";
import { componentsOf } from "@/features/config/summary";
import { fr } from "./french";
import type { Lang } from "./messages";
import schemaEn from "./server/config-schema.en.json";
import schemaFr from "./server/config-schema.fr.json";

type S = components["schemas"];

/** A JSON module types its strings as `string`, not as the schema's enums: `nestor admin mocks` wrote them from it. */
export const SCHEMAS: Record<Lang, S["ConfigSchemaOut"]> = {
  fr: schemaFr as S["ConfigSchemaOut"],
  en: schemaEn as S["ConfigSchemaOut"],
};

/** The secrets the vault keeps: their value and their age in minutes. The file refers to each but the last. */
export const SECRETS = {
  "models.elevenlabs.api_key": ["sk_e1d0a8c7b6f5", 60 * 24 * 30],
  "channels.discord.token": ["MTE5ODc2NTQzMjEw.GkT9aB.discord", 60 * 24 * 18],
  "channels.slack.app_token": ["xapp-1-A07RICHIE-7d2f41c9", 60 * 24 * 16],
  "channels.slack.bot_token": ["xoxb-4127-richie-9c0e2b", 60 * 24 * 16],
  "channels.matrix.token": ["syt_cmljaGll_b41f7a22", 60 * 24 * 15],
  "channels.whatsapp.token": ["EAAGm0PX4ZCpsBAwhatsapp", 60 * 24 * 14],
  "channels.whatsapp.verify_token": ["martin-verify-51c8", 60 * 24 * 14],
  "channels.whatsapp.app_secret": ["9f1c2e7ab4d05836", 60 * 24 * 14],
  "channels.email.password": ["hx7-richie-mailbox", 60 * 24 * 13],
  "channels.ntfy.token": ["tk_3f9a7d2f51c8", 60 * 24 * 11],
  "channels.webhook.secret": ["whsec_richie_says_2b77", 60 * 24 * 11],
  "channels.openai-api.keys.mathis": ["nsk-mathis-5e6b70a04f12", 60 * 24 * 7],
  "executors.hermes.api_key": ["hermes-7c0f2b91", 60 * 24 * 12],
  "tools.recipes.token": ["eyJhbGciOiJIUzI1NiJ9.recipes", 60 * 24 * 12],
  "inbound.webhooks.washing-machine.secret": ["whsec_washing_h5e0", 60 * 24 * 20],
  "home.token": ["eyJhbGciOiJIUzI1NiJ9.home", 60 * 24 * 12],
  // kept from a server nobody plugs in any more: the one secret nothing uses
  "github.token": ["ghp_unused0000", 60 * 24 * 40],
} as const satisfies Record<string, readonly [string, number]>;

/** The variables of the process's environment the file may refer to. */
export const ENVIRON = ["MODEL_API_KEY", "TELEGRAM_TOKEN"] as const;

/** References as a configuration file writes them: only to what the vault and the environment hold. */
const vault = (name: keyof typeof SECRETS) => `\${secret:${name}}`;
const environ = (name: (typeof ENVIRON)[number]) => `\${${name}}`;

/** Richie's household, as its `richie.yaml` reads. */
export function document(): ConfigDocument {
  return {
    data_dir: "data/richie",
    persona: {
      name: "Richie",
      locale: "en",
      language: "English",
      timezone: "UTC",
      character:
        "You are Richie, the Martin household's assistant. You speak plainly, warmly and with a touch of humour, and you get to the point.",
    },
    // each person by the accounts the channels below know them by, and the one written to first
    household: [
      {
        id: "mathis",
        name: "Mathis",
        accounts: [
          "telegram:@mathis_l",
          "slack:U04MATHIS7",
          "matrix:@mathis:matrix.martin.family",
          "email:mathis@martin.family",
          "openai-api:mathis",
        ],
        reach: "telegram:@mathis_l",
      },
      {
        id: "lea",
        name: "Léa",
        accounts: ["telegram:@lea_martin", "signal:+33655504102"],
        reach: "telegram:@lea_martin",
      },
      {
        id: "jules",
        name: "Jules",
        accounts: ["discord:jules.lbt"],
        reach: "ntfy:jules-martin-3f9a",
        may_message: ["mathis", "lea", "odile"],
      },
      {
        id: "odile",
        name: "Odile",
        accounts: ["telegram:@odile.m", "whatsapp:33655504977"],
        reach: "telegram:@odile.m",
      },
    ],
    models: {
      sonnet: {
        type: "language",
        provider: "openai-compatible",
        base_url: "https://openrouter.ai/api/v1",
        api_key: environ("MODEL_API_KEY"),
        model: "anthropic/claude-sonnet-4.6",
        vision: true,
        fallback: "haiku",
        extra_body: { provider: { order: ["anthropic"] } },
      },
      haiku: {
        type: "language",
        provider: "openai-compatible",
        base_url: "https://openrouter.ai/api/v1",
        api_key: environ("MODEL_API_KEY"),
        model: "anthropic/claude-haiku-4.5",
        vision: true,
      },
      voices: { type: "speaker", provider: "sherpa-onnx", model: "titanet-small", threads: 2 },
      scribe: {
        type: "transcription",
        provider: "elevenlabs",
        api_key: vault("models.elevenlabs.api_key"),
        model: "scribe_v2_realtime",
        language: "en",
      },
      victor: {
        type: "speech",
        provider: "elevenlabs",
        api_key: vault("models.elevenlabs.api_key"),
        voice_id: "Xb7hH8MSUJpSbSDYk0k2",
        model: "eleven_v4_turbo",
      },
    },
    agent: { spoken: "haiku", written: "sonnet" },
    alerts: { model: "haiku" },
    channels: [
      {
        kind: "satellites",
        port: 8471,
        public_url: "http://richie.local:8471",
        voice: {
          transcription: "scribe",
          speech: "victor",
          stt_fallback: "I can't hear you very well, my connection is playing up.",
        },
      },
      { kind: "web" },
      {
        kind: "telegram",
        token: environ("TELEGRAM_TOKEN"),
        apology: "Oops, something went wrong on my side. Can you try again?",
      },
      { kind: "discord", token: vault("channels.discord.token") },
      {
        kind: "slack",
        app_token: vault("channels.slack.app_token"),
        bot_token: vault("channels.slack.bot_token"),
      },
      { kind: "matrix", homeserver: "https://matrix.martin.family", token: vault("channels.matrix.token") },
      { kind: "signal", url: "http://signal-cli.local:8080", number: "+33655504217" },
      {
        kind: "whatsapp",
        phone_number_id: "104455512904218",
        token: vault("channels.whatsapp.token"),
        verify_token: vault("channels.whatsapp.verify_token"),
        app_secret: vault("channels.whatsapp.app_secret"),
        port: 8473,
      },
      {
        kind: "email",
        address: "richie@martin.family",
        username: "richie@martin.family",
        password: vault("channels.email.password"),
        imap_host: "imap.martin.family",
        smtp_host: "smtp.martin.family",
        smtp_port: 587,
        smtp_security: "starttls",
      },
      { kind: "ntfy", url: "https://ntfy.sh", token: vault("channels.ntfy.token") },
      {
        kind: "webhook",
        url: "http://homeassistant.local:8123/api/webhook/richie-says",
        secret: vault("channels.webhook.secret"),
      },
      { kind: "openai-api", keys: { mathis: vault("channels.openai-api.keys.mathis") }, port: 8472 },
    ],
    executors: [
      {
        kind: "hermes",
        base_url: "http://hermes.local:8642/v1",
        api_key: vault("executors.hermes.api_key"),
        model: "hermes-agent",
        description: fr(
          "search the web and browse sites, run code in its own container",
          "chercher sur le web et naviguer sur des sites, exécuter du code dans son conteneur",
        ),
        nestor_mcp: true,
      },
      {
        kind: "codex",
        command: ["ssh", "codex@vps.martin.family", "codex", "app-server", "proxy"],
        working_directory: "/srv/codex/work",
        description: fr(
          "run the home server: deploy the sites, read the logs",
          "s'occuper du serveur : déployer les sites, lire les journaux",
        ),
        sandbox: "workspace-write",
      },
      {
        kind: "claude-code",
        working_directory: "/home/mathis/projects",
        description: fr(
          "read, change and test the code of the household's projects",
          "lire, modifier et tester le code des projets du foyer",
        ),
        permission_mode: "acceptEdits",
        allowed_tools: ["Read", "Edit", "Bash(pnpm *)", "Bash(git *)"],
        max_budget_usd: 2,
      },
    ],
    tools: [
      {
        kind: "mcp",
        name: "recipes",
        url: "http://192.168.1.20:8808/mcp_server/sse",
        transport: "sse",
        token: vault("tools.recipes.token"),
        risks: { add_recipe: "write", delete_recipe: "sensitive" },
        headers: { "X-Household": "martin-home-7d2f" },
      },
      { kind: "open-meteo", home: "Lyon" },
      { kind: "openstreetmap", home: "Lyon" },
      { kind: "web-pages", timeout_s: 20 },
      { kind: "exa" },
    ],
    inbound: [
      {
        kind: "rss",
        name: "feeds",
        feeds: [
          { name: "LWN", url: "https://lwn.net/headlines/rss" },
          { name: "Home Assistant", url: "https://www.home-assistant.io/atom.xml" },
        ],
        every_s: 900,
      },
      {
        kind: "web-page",
        name: "pages",
        pages: [{ name: "summer camp", url: "https://www.lyon.fr/enfance-et-education/centres-de-loisirs" }],
        every_s: 3600,
      },
      {
        kind: "webhook",
        name: "webhooks",
        hooks: [
          {
            name: "washing-machine",
            kind: "washing-machine",
            secret: vault("inbound.webhooks.washing-machine.secret"),
          },
        ],
        port: 8474,
      },
    ],
    home: {
      kind: "home-assistant",
      url: "http://homeassistant.local:8123",
      token: vault("home.token"),
      people: { mathis: "person.mathis", lea: "person.lea", jules: "person.jules" },
      rooms: { mathis: "sensor.mathis_area", lea: "sensor.lea_area", jules: "sensor.jules_area" },
      sensitive: {
        domains: ["lock", "alarm_control_panel"],
        device_classes: ["garage", "gate", "door"],
        names: ["porte"],
      },
    },
    connectors: [{ kind: "google" }, { kind: "microsoft" }, { kind: "dav" }, { kind: "imap" }, { kind: "mcp" }],
    initiative: { quiet_hours: "22:30-07:30", main_room: "living room" },
    admin: { host: "0.0.0.0", port: 8470, public_url: "https://nestor.martin.family" },
  };
}

// -- what a document says exists ---------------------------------------------------------------------

/** The slots in the order Nestor builds them. */
const BUILT = ["models", "executors", "channels", "tools", "inbound", "home", "connectors"];

/** The mark an adapter goes by when it is not its kind's. */
const MARKS: Record<string, string> = { "openai-api": "openai", "home-assistant": "homeassistant" };

/** A component the file plugs in, as Nestor names it once built. */
export interface Plugged {
  slot: Component["slot"];
  name: string; // the entry's `name`, a model's key, else its plugin
  plugin: string;
  brand: string;
  model_type: ModelType | null;
  fallback: string | null;
  entry: Record<string, unknown>;
}

/** Every component a document plugs in, in build order. */
export function plugged(doc: ConfigDocument): Plugged[] {
  return BUILT.flatMap((key) => {
    const slot = SCHEMAS.en.slots[key] as Slot | undefined;
    if (!slot) return [];
    return componentsOf(slot, key, doc).map((c): Plugged => {
      const named = typeof c.entry.name === "string" && c.entry.name ? c.entry.name : c.plugin;
      return {
        slot: slot.family as Component["slot"],
        name: slot.shape === "named" ? String(c.at) : slot.shape === "one" ? key : named,
        plugin: c.plugin,
        brand: MARKS[c.plugin] ?? c.mark,
        model_type: (slot.model_types[c.plugin] as ModelType | undefined) ?? null,
        fallback: typeof c.entry.fallback === "string" ? c.entry.fallback : null,
        entry: c.entry,
      };
    });
  });
}

/** The entries of a slot the file holds as a list. */
export function entries(doc: ConfigDocument, key: string): Record<string, unknown>[] {
  const value = doc[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

/** The people of the file: who they are, the accounts channels know them by, where they are written to first. */
export function household(
  doc: ConfigDocument,
): { id: string; name: string; accounts: string[]; reach: string | null }[] {
  return entries(doc, "household").map((p) => ({
    id: String(p.id),
    name: String(p.name),
    accounts: Array.isArray(p.accounts) ? p.accounts.map(String) : [],
    reach: typeof p.reach === "string" ? p.reach : null,
  }));
}

/** What the inbound sources of the file bring to alerts, beside the mail of connected accounts. */
export function brought(doc: ConfigDocument): string[] {
  const kinds = entries(doc, "inbound").flatMap((source) => {
    if (source.kind === "rss") return ["feed"];
    if (source.kind === "web-page") return ["page"];
    const hooks = Array.isArray(source.hooks) ? source.hooks.filter(isRecord) : [];
    return hooks.map((hook) => String(hook.kind));
  });
  return [...new Set(kinds)];
}

/** The address the admin is reached at from outside, when the file gives one. */
export function publicUrl(doc: ConfigDocument): string | null {
  const admin = doc.admin;
  return isRecord(admin) && typeof admin.public_url === "string" ? admin.public_url : null;
}
