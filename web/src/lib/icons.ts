/**
 * What each icon means, in one place: event kinds, statuses, capabilities, sections.
 * Icons carry meaning next to a word; they are never the only signal and never decoration.
 */
import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BookMarked,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Hourglass,
  House,
  KeyRound,
  Megaphone,
  MessageSquareText,
  Mic,
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

export interface KindStyle {
  icon: LucideIcon;
  /** Tailwind text colour class of the kind's accent (tokens.css `--kind-*`). */
  tone: string;
  /** The rail colour behind a story of this kind. */
  rail: string;
}

export const KIND: Record<string, KindStyle> = {
  conversation: { icon: MessageSquareText, tone: "text-ink", rail: "bg-ink/25" },
  delivery: { icon: Megaphone, tone: "text-ember", rail: "bg-ember/50" },
  tool: { icon: Wrench, tone: "text-ink-muted", rail: "bg-rule-strong" },
  task: { icon: Workflow, tone: "text-kind-task", rail: "bg-kind-task/45" },
  watch: { icon: Radar, tone: "text-kind-watch", rail: "bg-kind-watch/45" },
  memory: { icon: BookMarked, tone: "text-sage", rail: "bg-sage/45" },
  connection: { icon: Plug, tone: "text-ink-muted", rail: "bg-rule-strong" },
  presence: { icon: House, tone: "text-ink-muted", rail: "bg-rule-strong" },
  satellite: { icon: RadioTower, tone: "text-ink-muted", rail: "bg-rule-strong" },
  observation: { icon: ScanEye, tone: "text-ink-faint", rail: "bg-rule" },
  account: { icon: KeyRound, tone: "text-ink-muted", rail: "bg-rule" },
};

export function kindStyle(kind: string): KindStyle {
  return KIND[kind] ?? { icon: CircleDashed, tone: "text-ink-muted", rail: "bg-rule" };
}

export const STATUS_ICON = {
  ok: CircleCheck,
  attention: KeyRound,
  error: CircleAlert,
  pending: Hourglass,
  idle: CircleSlash,
} satisfies Record<string, LucideIcon>;

export const CAPABILITY_ICON: Record<string, LucideIcon> = {
  "audio.capture": Mic,
  "audio.playback": Volume2,
  "audio.speech_activity": AudioLines,
  "vision.person_detection": ScanFace,
  "expression.emotion": Smile,
  "motion.head": Move3d,
};

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
