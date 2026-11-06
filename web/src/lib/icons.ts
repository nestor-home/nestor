/**
 * What each icon means, in one place: event kinds, statuses, capabilities, sections.
 * Icons carry meaning next to a word; they are never the only signal and never decoration.
 */
import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  AudioLines,
  BookMarked,
  Bot,
  CircleAlert,
  CircleArrowUp,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Hourglass,
  House,
  Keyboard,
  KeyRound,
  Lightbulb,
  Megaphone,
  MessageSquareText,
  Mic,
  MonitorSmartphone,
  Move3d,
  Plug,
  Radar,
  RadioTower,
  ScanEye,
  ScanFace,
  ScrollText,
  Server,
  SlidersHorizontal,
  Smile,
  Sun,
  Users,
  Volume2,
  Workflow,
  Wrench,
} from "lucide-react";
import type { Kind } from "@/api";

export interface KindStyle {
  icon: LucideIcon;
  /** Tailwind text colour class of the kind's accent (tokens.css `--kind-*`). */
  tone: string;
  /** The rail colour behind a story of this kind. */
  rail: string;
}

/** Every kind the API sends (`Kind`): a new one fails the typecheck here until it has its look. */
export const KIND: Record<Kind, KindStyle> = {
  conversation: { icon: MessageSquareText, tone: "text-ink", rail: "bg-ink/25" },
  delivery: { icon: Megaphone, tone: "text-ember", rail: "bg-ember/50" },
  tool: { icon: Wrench, tone: "text-ink-muted", rail: "bg-rule-strong" },
  task: { icon: Workflow, tone: "text-kind-task", rail: "bg-kind-task/45" },
  watch: { icon: Radar, tone: "text-kind-watch", rail: "bg-kind-watch/45" },
  schedule: { icon: AlarmClock, tone: "text-ink-muted", rail: "bg-rule-strong" },
  memory: { icon: BookMarked, tone: "text-sage", rail: "bg-sage/45" },
  connection: { icon: Plug, tone: "text-ink-muted", rail: "bg-rule-strong" },
  presence: { icon: House, tone: "text-ink-muted", rail: "bg-rule-strong" },
  satellite: { icon: RadioTower, tone: "text-ink-muted", rail: "bg-rule-strong" },
  voice: { icon: AudioLines, tone: "text-ink-muted", rail: "bg-rule-strong" },
  observation: { icon: ScanEye, tone: "text-ink-faint", rail: "bg-rule" },
  account: { icon: KeyRound, tone: "text-ink-muted", rail: "bg-rule" },
  other: { icon: CircleDashed, tone: "text-ink-muted", rail: "bg-rule" },
};

export const kindStyle = (kind: Kind): KindStyle => KIND[kind];

export const STATUS_ICON = {
  ok: CircleCheck,
  attention: KeyRound,
  error: CircleAlert,
  pending: Hourglass,
  idle: CircleSlash,
} satisfies Record<string, LucideIcon>;

export const CAPABILITY_ICON: Record<string, LucideIcon> = {
  "text.input": Keyboard,
  "text.display": MessageSquareText,
  "audio.capture": Mic,
  "audio.playback": Volume2,
  "audio.speech_activity": AudioLines,
  "vision.person_detection": ScanFace,
  "expression.emotion": Smile,
  "motion.head": Move3d,
  "device.identify": Lightbulb,
  "device.update": CircleArrowUp,
};

/**
 * What a satellite is, from what it can do, for a device whose maker has no logo: the body before the
 * screen, the screen before the sound; the capability's own icon where it already says it.
 */
export const DEVICE_KIND: [string[], LucideIcon][] = [
  [["motion.head", "expression.emotion"], Bot],
  [["text.display", "text.input"], MonitorSmartphone],
  [["audio.playback"], CAPABILITY_ICON["audio.playback"] as LucideIcon],
  [["audio.capture"], CAPABILITY_ICON["audio.capture"] as LucideIcon],
  [["vision.person_detection"], CAPABILITY_ICON["vision.person_detection"] as LucideIcon],
];

export const SECTION_ICON = {
  "/": Sun,
  "/journal": ScrollText,
  "/people": Users,
  "/memories": BookMarked,
  "/watches": Radar,
  "/tasks": Workflow,
  "/connections": Plug,
  "/satellites": RadioTower,
  "/system": Server,
  "/accounts": KeyRound,
  "/config": SlidersHorizontal,
} satisfies Record<string, LucideIcon>;
