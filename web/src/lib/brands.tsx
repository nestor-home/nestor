/**
 * Every third-party mark the admin shows, in one place, from the same sources as the site
 * (nestor-web `lib/brands.ts`). Marks identify an integration (nominative use) and are never Nestor's
 * own branding. Simple Icons (CC0) for services; Lobe Icons (`@lobehub/icons-static-svg`, MIT, by
 * LobeHub) for AI providers, which Simple Icons partly dropped at the brands' request; for a brand in
 * neither set its official mark, kept in src/assets/brands/ with its source and drawn in one colour;
 * a brand without any published mark gets a text monogram, never a drawn imitation. A neutral lucide
 * glyph stands for what is not a brand (any mailbox, the voice). Drawn in ink; `colour` shows the
 * brand's own colour where it reads on both themes.
 *
 * Keys are the `brand` slugs the API sends (connectors, channels, executors, models, speech,
 * satellites); `brandOf(kind)` also maps plugin kinds and the API's other spellings.
 */
import anthropicSvg from "@lobehub/icons-static-svg/icons/anthropic.svg?raw";
import claudeSvg from "@lobehub/icons-static-svg/icons/claude.svg?raw";
import codexSvg from "@lobehub/icons-static-svg/icons/codex.svg?raw";
import elevenlabsSvg from "@lobehub/icons-static-svg/icons/elevenlabs.svg?raw";
import geminiSvg from "@lobehub/icons-static-svg/icons/gemini.svg?raw";
import groqSvg from "@lobehub/icons-static-svg/icons/groq.svg?raw";
import hermesagentSvg from "@lobehub/icons-static-svg/icons/hermesagent.svg?raw";
import lmstudioSvg from "@lobehub/icons-static-svg/icons/lmstudio.svg?raw";
import mistralSvg from "@lobehub/icons-static-svg/icons/mistral.svg?raw";
import modelscopeSvg from "@lobehub/icons-static-svg/icons/modelscope.svg?raw";
import nvidiaSvg from "@lobehub/icons-static-svg/icons/nvidia.svg?raw";
import ollamaSvg from "@lobehub/icons-static-svg/icons/ollama.svg?raw";
import openaiSvg from "@lobehub/icons-static-svg/icons/openai.svg?raw";
import openrouterSvg from "@lobehub/icons-static-svg/icons/openrouter.svg?raw";
import vllmSvg from "@lobehub/icons-static-svg/icons/vllm.svg?raw";
import type { LucideIcon } from "lucide-react";
import { Cpu, Globe, KeyRound, Mail, Mic, Plug, RadioTower } from "lucide-react";
import {
  type SimpleIcon,
  siAnthropic,
  siCplusplus,
  siDeepgram,
  siDocker,
  siElevenlabs,
  siEspressif,
  siGithub,
  siGmail,
  siGoogle,
  siGooglecalendar,
  siGooglegemini,
  siHomeassistant,
  siLinear,
  siLmstudio,
  siMistralai,
  siModelcontextprotocol,
  siNotion,
  siNvidia,
  siOpenrouter,
  siPipecat,
  siPython,
  siRaspberrypi,
  siRust,
  siSqlite,
  siTelegram,
  siTypescript,
  siVllm,
  siWebrtc,
  siWhatsapp,
} from "simple-icons";
import cartesiaSvg from "@/assets/brands/cartesia.svg?raw";
import gradiumSvg from "@/assets/brands/gradium.svg?raw";
import llamaCppSvg from "@/assets/brands/llama-cpp.svg?raw";
import piperSvg from "@/assets/brands/piper.svg?raw";
import { type Args, tr } from "@/i18n/runtime";
import { cn } from "@/lib/utils";

/** How a mark is drawn: paths in a 24×24 box, an official mark in its own box, a monogram or a glyph. */
type Mark =
  | { paths: readonly string[]; evenodd?: boolean }
  | { official: { viewBox: string; shapes: string } }
  | { monogram: string }
  | { glyph: LucideIcon };

/** A mark, its accessible label (a brand's own name, or a Fluent message for what is not a brand) and its colour. */
type Brand = { mark: Mark; hex?: string } & ({ name: string } | { message: string; args?: Args });

/** Relative luminance of a `RRGGBB` colour (WCAG). */
function luminance(hex: string): number {
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The brand's colour, only when it stays legible on paper and on ink (black or white marks stay in ink). */
function legible(icon: SimpleIcon): string | undefined {
  const l = luminance(icon.hex);
  return l > 0.04 && l < 0.7 ? `#${icon.hex}` : undefined;
}

const simple = (name: string, icon: SimpleIcon): Brand => ({ name, mark: { paths: [icon.path] }, hex: legible(icon) });
/** A Lobe Icons mark (monochrome, 24×24), with the brand's colour from Simple Icons when it has one. */
const lobe = (name: string, svg: string, colour?: SimpleIcon): Brand => {
  const paths = [...svg.matchAll(/<path[^>]*\sd="([^"]+)"/g)].map((m) => m[1] ?? "");
  if (paths.length === 0) throw new Error(`[brands] no path in the ${name} mark`);
  return { name, mark: { paths, evenodd: true }, hex: colour ? legible(colour) : undefined };
};
/** An official mark from src/assets/brands/: its viewBox and the shapes inside its root. */
const official = (name: string, svg: string): Brand => {
  const viewBox = svg.match(/<svg[^>]*\sviewBox="([^"]+)"/)?.[1];
  const shapes = svg.match(/<svg[^>]*>([\s\S]*)<\/svg>/)?.[1];
  if (!viewBox || !shapes) throw new Error(`[brands] the ${name} mark has no viewBox or shapes`);
  return { name, mark: { official: { viewBox, shapes } } };
};
const monogram = (name: string, letters: string): Brand => ({ name, mark: { monogram: letters } });
const glyph = (name: string, icon: LucideIcon): Brand => ({ name, mark: { glyph: icon } });
const concept = (message: string, icon: LucideIcon, args?: Args): Brand => ({ message, args, mark: { glyph: icon } });
/** A satellite SDK, named by its language in the reader's word order. */
const sdk = (language: string, icon: SimpleIcon): Brand => ({
  message: "brand-sdk",
  args: { language },
  mark: { paths: [icon.path] },
  hex: legible(icon),
});

const BRANDS = {
  // services, channels and the home
  gmail: simple("Gmail", siGmail),
  google: simple("Google", siGoogle),
  "google-calendar": simple("Google Calendar", siGooglecalendar),
  telegram: simple("Telegram", siTelegram),
  whatsapp: simple("WhatsApp", siWhatsapp),
  "home-assistant": simple("Home Assistant", siHomeassistant),
  matter: monogram("Matter", "M"),
  mcp: simple("Model Context Protocol", siModelcontextprotocol),
  linear: simple("Linear", siLinear),
  github: simple("GitHub", siGithub),
  notion: simple("Notion", siNotion),
  imap: glyph("IMAP", Mail),
  oauth: glyph("OAuth", KeyRound),
  webrtc: simple("WebRTC", siWebrtc),
  web: glyph("Web", Globe),
  satellites: concept("brand-satellites", RadioTower),
  voice: concept("brand-voice", Mic),
  // executors
  hermes: lobe("Hermes (Nous Research)", hermesagentSvg),
  codex: lobe("Codex", codexSvg),
  // model providers
  "openai-compatible": concept("brand-openai-compatible", Cpu),
  openrouter: lobe("OpenRouter", openrouterSvg, siOpenrouter),
  openai: lobe("OpenAI", openaiSvg),
  anthropic: lobe("Anthropic", anthropicSvg, siAnthropic),
  claude: lobe("Claude", claudeSvg),
  mistral: lobe("Mistral", mistralSvg, siMistralai),
  gemini: lobe("Gemini", geminiSvg, siGooglegemini),
  groq: lobe("Groq", groqSvg),
  ollama: lobe("Ollama", ollamaSvg),
  "lm-studio": lobe("LM Studio", lmstudioSvg, siLmstudio),
  vllm: lobe("vLLM", vllmSvg, siVllm),
  "llama-cpp": official("llama.cpp", llamaCppSvg),
  // speech: voices, transcription, turn taking
  elevenlabs: lobe("ElevenLabs", elevenlabsSvg, siElevenlabs),
  cartesia: official("Cartesia", cartesiaSvg),
  gradium: official("Gradium", gradiumSvg),
  deepgram: simple("Deepgram", siDeepgram),
  whisper: lobe("Whisper", openaiSvg), // OpenAI's model: its maker's mark
  piper: official("Piper", piperSvg),
  kokoro: monogram("Kokoro", "K"),
  silero: monogram("Silero VAD", "S"),
  "smart-turn": simple("Smart Turn (Pipecat)", siPipecat), // Pipecat's model: its maker's mark
  // voice recognition: the publisher of each model, else the runtime that runs it
  nvidia: lobe("NVIDIA", nvidiaSvg, siNvidia),
  modelscope: lobe("ModelScope (Alibaba)", modelscopeSvg),
  "sherpa-onnx": monogram("sherpa-onnx", "so"),
  // devices and their software
  reachy: monogram("Reachy Mini (Pollen Robotics)", "R"),
  "raspberry-pi": simple("Raspberry Pi", siRaspberrypi),
  espressif: simple("ESP32 (Espressif)", siEspressif),
  python: sdk("Python", siPython),
  typescript: sdk("TypeScript", siTypescript),
  rust: sdk("Rust", siRust),
  cpp: sdk("C++", siCplusplus),
  // storage and installation
  sqlite: simple("SQLite", siSqlite),
  litestream: monogram("Litestream", "L"),
  docker: simple("Docker", siDocker),
} satisfies Record<string, Brand>;

export type BrandSlug = keyof typeof BRANDS;

/** Plugin kinds, channel prefixes and the API's other spellings, to brand slugs. */
const ALIASES: Record<string, BrandSlug> = {
  homeassistant: "home-assistant",
  "pollen-robotics": "reachy",
  "reachy-mini": "reachy",
  "elevenlabs-transcription": "elevenlabs",
  "elevenlabs-speech": "elevenlabs",
  lmstudio: "lm-studio",
  "llama.cpp": "llama-cpp",
  "nestor-satellite-python": "python",
  "nestor-satellite-typescript": "typescript",
  "nestor-satellite-rust": "rust",
};

export function brandOf(kind: string | null | undefined): BrandSlug | null {
  if (!kind) return null;
  const key = kind.split(":")[0] ?? kind;
  if (key in BRANDS) return key as BrandSlug;
  return ALIASES[key] ?? null;
}

/** Whether the brand has a published logo (a monogram stands in for one that has none). */
export function hasLogo(slug: BrandSlug): boolean {
  const brand: Brand = BRANDS[slug];
  return !("monogram" in brand.mark);
}

export function brandName(slug: BrandSlug): string {
  const brand: Brand = BRANDS[slug];
  return "name" in brand ? brand.name : tr(brand.message, brand.args);
}

/**
 * A brand's mark at the size of the other icons (16px in UI text unless `className` sizes it).
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
  const { mark, hex }: Brand = BRANDS[brand];
  const name = brandName(brand);
  const a11y = label ? { role: "img", "aria-label": name } : { "aria-hidden": true as const };
  const classes = cn("size-4 shrink-0", className);
  const style = colour && hex ? { color: hex } : undefined;
  if ("glyph" in mark) {
    const Glyph = mark.glyph;
    return <Glyph className={classes} {...a11y} />;
  }
  const title = label ? <title>{name}</title> : null;
  if ("official" in mark) {
    return (
      // biome-ignore lint/a11y/noSvgWithoutTitle: titled when labelled, hidden from assistive tech otherwise
      <svg viewBox={mark.official.viewBox} className={cn(classes, "fill-current")} style={style} {...a11y}>
        {title}
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a mark bundled from src/assets/brands, never from data */}
        <g dangerouslySetInnerHTML={{ __html: mark.official.shapes }} />
      </svg>
    );
  }
  if ("monogram" in mark) {
    return (
      // biome-ignore lint/a11y/noSvgWithoutTitle: titled when labelled, hidden from assistive tech otherwise
      <svg viewBox="0 0 24 24" className={classes} {...a11y}>
        {title}
        <rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <text
          x="12"
          y="16.2"
          textAnchor="middle"
          fontSize="12"
          fontWeight="600"
          fill="currentColor"
          className="font-mono"
        >
          {mark.monogram}
        </text>
      </svg>
    );
  }
  return (
    // biome-ignore lint/a11y/noSvgWithoutTitle: titled when labelled, hidden from assistive tech otherwise
    <svg
      viewBox="0 0 24 24"
      className={cn(classes, "fill-current")}
      fillRule={mark.evenodd ? "evenodd" : undefined}
      style={style}
      {...a11y}
    >
      {title}
      {mark.paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

/** The mark for a kind or channel, or a neutral plug when nothing is known about it. */
export function KindMark({ kind, className, label = true }: { kind: string; className?: string; label?: boolean }) {
  const slug = brandOf(kind);
  if (slug) return <BrandMark brand={slug} className={className} label={label} />;
  return (
    <Plug className={cn("size-4 shrink-0", className)} aria-hidden={!label} aria-label={label ? kind : undefined} />
  );
}
