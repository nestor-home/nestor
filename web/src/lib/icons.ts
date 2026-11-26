/**
 * What each icon means, in one place: event kinds, statuses, capabilities, sections.
 * Icons carry meaning next to a word; they are never the only signal and never decoration.
 */
import type { LucideIcon } from "lucide-react";
import {
  Archive,
  AudioLines,
  BellRing,
  BookMarked,
  Bot,
  CircleAlert,
  CircleArrowUp,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Coins,
  Ear,
  Flag,
  FolderKanban,
  Hash,
  Heading,
  Hourglass,
  House,
  Image,
  Keyboard,
  KeyRound,
  Lightbulb,
  ListFilter,
  Megaphone,
  Merge,
  MessageSquareText,
  MessagesSquare,
  Mic,
  MonitorSmartphone,
  Move3d,
  PenLine,
  Plug,
  RadioTower,
  ScanEye,
  ScanFace,
  Smile,
  Sparkles,
  Speech,
  UserRound,
  Users,
  Video,
  Volume2,
  Waypoints,
  Workflow,
  Wrench,
} from "lucide-react";
import type { Kind, ModelType, Retirement, Shelf } from "@/api";

export interface KindStyle {
  icon: LucideIcon;
  /** Tailwind text colour class of the kind's accent (tokens.css `--kind-*`). */
  tone: string;
  /** The rail colour behind a story of this kind. */
  rail: string;
}

/** Every kind the API sends (`Kind`): a new one fails the typecheck here until it has its look. */
const KIND: Record<Kind, KindStyle> = {
  conversation: { icon: MessageSquareText, tone: "text-ink", rail: "bg-ink/25" },
  delivery: { icon: Megaphone, tone: "text-ember", rail: "bg-ember/50" },
  tool: { icon: Wrench, tone: "text-ink-muted", rail: "bg-rule-strong" },
  task: { icon: Workflow, tone: "text-kind-task", rail: "bg-kind-task/45" },
  alert: { icon: BellRing, tone: "text-kind-alert", rail: "bg-kind-alert/45" },
  memory: { icon: BookMarked, tone: "text-sage", rail: "bg-sage/45" },
  connection: { icon: Plug, tone: "text-ink-muted", rail: "bg-rule-strong" },
  presence: { icon: House, tone: "text-ink-muted", rail: "bg-rule-strong" },
  satellite: { icon: RadioTower, tone: "text-ink-muted", rail: "bg-rule-strong" },
  voice: { icon: AudioLines, tone: "text-ink-muted", rail: "bg-rule-strong" },
  observation: { icon: ScanEye, tone: "text-ink-faint", rail: "bg-rule" },
  account: { icon: KeyRound, tone: "text-ink-muted", rail: "bg-rule" },
  usage: { icon: Coins, tone: "text-ink-faint", rail: "bg-rule" },
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
  "video.capture": Video,
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
  [["video.capture"], CAPABILITY_ICON["video.capture"] as LucideIcon],
];

/** What each type of model does, as a mark: a new type fails the typecheck here until it has its look. */
export const MODEL_TYPE_ICON: Record<ModelType, LucideIcon> = {
  language: MessagesSquare,
  embedding: Waypoints,
  speaker: AudioLines,
  transcription: Ear,
  speech: Volume2,
  image: Image,
};

/** The roles a model can hold, by the configuration field that names it; any other role gets the plain mark. */
const ROLE_ICON: Record<string, LucideIcon> = {
  spoken: Speech,
  written: PenLine,
  titles: Heading,
  transcription: Ear,
  speech: Volume2,
  images: Image,
  model: ListFilter,
  consolidation: BookMarked,
  embedder: Waypoints,
};

export const roleIcon = (field: string): LucideIcon => ROLE_ICON[field] ?? Sparkles;

/** Where a memory is filed, by its shelf: a new shelf fails the typecheck here until it has its look. */
export const SHELF_ICON: Record<Shelf, LucideIcon> = {
  people: UserRound,
  home: House,
  household: Users,
  projects: FolderKanban,
  topics: Hash,
};

/** Why a memory was retired: merged into another, found outdated, or its task ended. */
export const RETIREMENT_ICON: Record<Retirement, LucideIcon> = {
  merged: Merge,
  stale: Archive,
  ended: Flag,
};
