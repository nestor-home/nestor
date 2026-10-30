/**
 * Every third-party mark the admin shows, in one place. Marks identify an integration
 * (nominative use) and are never Nestor's own branding. Simple Icons (CC0 paths) where the brand
 * exists there, a neutral lucide glyph otherwise; monochrome in ink unless `colour` is asked.
 *
 * Keys are the `brand` slug the API will expose on connectors, channels, executors and providers;
 * until it does, `brandOf(kind)` maps today's kinds.
 */
import type { LucideIcon } from "lucide-react";
import {
  AudioWaveform,
  Bot,
  Cpu,
  DatabaseBackup,
  Feather,
  Globe,
  KeyRound,
  Mail,
  Mic,
  Network,
  Plug,
} from "lucide-react";
import {
  type SimpleIcon,
  siAnthropic,
  siClaude,
  siCplusplus,
  siDocker,
  siElevenlabs,
  siEspressif,
  siGmail,
  siGoogle,
  siGooglecalendar,
  siGooglegemini,
  siHomeassistant,
  siModelcontextprotocol,
  siOpenrouter,
  siPython,
  siRaspberrypi,
  siRust,
  siSqlite,
  siTelegram,
  siTypescript,
  siWebrtc,
  siWhatsapp,
} from "simple-icons";
import { cn } from "@/lib/utils";

interface Brand {
  name: string; // the accessible label
  mark: SimpleIcon | LucideIcon;
}

const BRANDS = {
  gmail: { name: "Gmail", mark: siGmail },
  google: { name: "Google", mark: siGoogle },
  "google-calendar": { name: "Google Agenda", mark: siGooglecalendar },
  gemini: { name: "Gemini (Vertex AI)", mark: siGooglegemini },
  telegram: { name: "Telegram", mark: siTelegram },
  whatsapp: { name: "WhatsApp", mark: siWhatsapp },
  "home-assistant": { name: "Home Assistant", mark: siHomeassistant },
  matter: { name: "Matter", mark: Network },
  hermes: { name: "Hermes (Nous Research)", mark: Feather },
  codex: { name: "Codex", mark: Cpu },
  openrouter: { name: "OpenRouter", mark: siOpenrouter },
  anthropic: { name: "Anthropic", mark: siAnthropic },
  claude: { name: "Claude", mark: siClaude },
  "openai-compatible": { name: "API compatible OpenAI", mark: Cpu },
  elevenlabs: { name: "ElevenLabs", mark: siElevenlabs },
  silero: { name: "Silero VAD", mark: AudioWaveform },
  "smart-turn": { name: "Smart Turn", mark: AudioWaveform },
  mcp: { name: "Model Context Protocol", mark: siModelcontextprotocol },
  imap: { name: "IMAP", mark: Mail },
  oauth: { name: "OAuth", mark: KeyRound },
  webrtc: { name: "WebRTC", mark: siWebrtc },
  voice: { name: "Voix", mark: Mic },
  web: { name: "Web", mark: Globe },
  reachy: { name: "Reachy Mini (Pollen Robotics)", mark: Bot },
  "raspberry-pi": { name: "Raspberry Pi", mark: siRaspberrypi },
  espressif: { name: "ESP32 (Espressif)", mark: siEspressif },
  python: { name: "SDK Python", mark: siPython },
  typescript: { name: "SDK TypeScript", mark: siTypescript },
  rust: { name: "SDK Rust", mark: siRust },
  cpp: { name: "SDK C++", mark: siCplusplus },
  sqlite: { name: "SQLite", mark: siSqlite },
  litestream: { name: "Litestream", mark: DatabaseBackup },
  docker: { name: "Docker", mark: siDocker },
} satisfies Record<string, Brand>;

export type BrandSlug = keyof typeof BRANDS;

/** Today's kinds and channel prefixes to brand slugs; `brand` from the API replaces this. */
const KIND_TO_BRAND: Record<string, BrandSlug> = {
  google: "gmail",
  gmail: "gmail",
  "google-calendar": "google-calendar",
  imap: "imap",
  mcp: "mcp",
  telegram: "telegram",
  whatsapp: "whatsapp",
  voice: "voice",
  web: "web",
  webrtc: "webrtc",
  hermes: "hermes",
  codex: "codex",
  "home-assistant": "home-assistant",
};

export function brandOf(kind: string | null | undefined): BrandSlug | null {
  if (!kind) return null;
  if (kind in BRANDS) return kind as BrandSlug;
  return KIND_TO_BRAND[kind.split(":")[0] ?? kind] ?? null;
}

export function brandName(slug: BrandSlug): string {
  return BRANDS[slug].name;
}

function isSimpleIcon(mark: Brand["mark"]): mark is SimpleIcon {
  return typeof mark === "object" && "path" in mark;
}

/**
 * A brand's mark at the size of the other icons (1em by default, 16px in UI text).
 * `label` false when the name is written next to it, so it is not read twice.
 */
export function BrandMark({
  brand,
  className,
  colour = false,
  label = true,
}: {
  brand: BrandSlug;
  className?: string;
  colour?: boolean;
  label?: boolean;
}) {
  const { name, mark } = BRANDS[brand];
  const a11y = label ? { role: "img", "aria-label": name } : { "aria-hidden": true as const };
  if (isSimpleIcon(mark)) {
    return (
      // biome-ignore lint/a11y/noSvgWithoutTitle: titled when labelled, hidden from assistive tech otherwise
      <svg
        viewBox="0 0 24 24"
        className={cn("size-4 shrink-0 fill-current", className)}
        style={colour ? { color: `#${mark.hex}` } : undefined}
        {...a11y}
      >
        {label ? <title>{name}</title> : null}
        <path d={mark.path} />
      </svg>
    );
  }
  const Glyph = mark;
  return <Glyph className={cn("size-4 shrink-0", className)} {...a11y} />;
}

/** The mark for a kind or channel, or a neutral plug when nothing is known about it. */
export function KindMark({ kind, className, label = true }: { kind: string; className?: string; label?: boolean }) {
  const slug = brandOf(kind);
  if (slug) return <BrandMark brand={slug} className={className} label={label} />;
  return (
    <Plug className={cn("size-4 shrink-0", className)} aria-hidden={!label} aria-label={label ? kind : undefined} />
  );
}
