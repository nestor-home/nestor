import type { LucideIcon } from "lucide-react";
import {
  BellRing,
  Check,
  CircleAlert,
  Filter,
  Inbox,
  Megaphone,
  Play,
  Plus,
  Send,
  StepForward,
  Volume2,
  X,
} from "lucide-react";
import type { JournalItem } from "@/api";
import { tr } from "@/i18n/runtime";

export interface StepLook {
  label: string;
  icon: LucideIcon;
  tone: string;
}

const SPOKEN = new Set(["voice"]);

/** How a step of a chain reads: a short label and a glyph, from the event type. */
export function stepLook(item: JournalItem): StepLook {
  const t = item.type.split(".").at(-1) ?? item.type;
  const followUp = item.message.args.follow_up === "yes";
  switch (t) {
    case "task_started":
      return { label: tr("step-task-started"), icon: Play, tone: "text-kind-task" };
    case "task_progressed":
      return { label: tr("step-task-progressed"), icon: StepForward, tone: "text-ink-muted" };
    case "task_ended":
      return item.outcome?.ok === false
        ? { label: tr("step-task-failed"), icon: X, tone: "text-brick" }
        : { label: tr("step-task-completed"), icon: Check, tone: "text-sage" };
    case "watch_created":
      return { label: tr("step-watch-created"), icon: Plus, tone: "text-kind-watch" };
    case "watch_triggered":
      return { label: tr("step-watch-triggered"), icon: Inbox, tone: "text-kind-watch" };
    case "watch_triaged":
      return { label: tr("step-watch-triaged"), icon: Filter, tone: "text-ink-muted" };
    case "delivery_considered":
      return {
        label: tr(followUp ? "step-follow-up" : "step-considered"),
        icon: followUp ? BellRing : Megaphone,
        tone: "text-ember",
      };
    case "delivered":
      return item.channels.some((c) => SPOKEN.has(c))
        ? { label: tr("step-delivered-spoken"), icon: Volume2, tone: "text-ember" }
        : { label: tr("step-delivered-written"), icon: Send, tone: "text-ember" };
    case "delivery_failed":
      return { label: tr("step-delivery-failed"), icon: CircleAlert, tone: "text-brick" };
    default:
      return { label: t.replace(/_/g, " "), icon: StepForward, tone: "text-ink-muted" };
  }
}
