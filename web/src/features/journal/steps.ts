import type { LucideIcon } from "lucide-react";
import {
  BellRing,
  Check,
  CircleAlert,
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
import { is } from "@/lib/events";
import { say } from "@/lib/messages";

export interface StepLook {
  label: string;
  icon: LucideIcon;
  tone: string;
  /** the small dot that carries the step's colour */
  dot: string;
}

const SPOKEN = new Set(["voice"]);

/** How a step of a chain reads: a short label and a glyph, from the event type. */
export function stepLook(item: JournalItem): StepLook {
  const followUp = item.message.args.follow_up === "yes";
  if (is(item, "taskStarted"))
    return { label: tr("step-task-started"), icon: Play, tone: "text-kind-task", dot: "bg-kind-task" };
  if (is(item, "taskProgressed"))
    return { label: tr("step-task-progressed"), icon: StepForward, tone: "text-ink-muted", dot: "bg-ink-faint" };
  if (is(item, "taskEnded"))
    return item.message.args.status === "failed"
      ? { label: tr("step-task-failed"), icon: X, tone: "text-brick", dot: "bg-brick" }
      : item.message.args.status === "cancelled"
        ? { label: tr("step-task-cancelled"), icon: X, tone: "text-ink-muted", dot: "bg-ink-faint" }
        : { label: tr("step-task-completed"), icon: Check, tone: "text-sage", dot: "bg-sage" };
  if (is(item, "taskDelivered"))
    return { label: tr("step-task-delivered"), icon: Send, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "watchCreated"))
    return { label: tr("step-watch-created"), icon: Plus, tone: "text-kind-watch", dot: "bg-kind-watch" };
  if (is(item, "watchTriggered"))
    return { label: tr("step-watch-triggered"), icon: Inbox, tone: "text-kind-watch", dot: "bg-kind-watch" };
  if (is(item, "considered"))
    return {
      label: tr(followUp ? "step-follow-up" : "step-considered"),
      icon: followUp ? BellRing : Megaphone,
      tone: "text-ember",
      dot: "bg-ember",
    };
  if (is(item, "delivered"))
    return item.channels.some((c) => SPOKEN.has(c))
      ? { label: tr("step-delivered-spoken"), icon: Volume2, tone: "text-ember", dot: "bg-ember" }
      : { label: tr("step-delivered-written"), icon: Send, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "deliveryFailed"))
    return { label: tr("step-delivery-failed"), icon: CircleAlert, tone: "text-brick", dot: "bg-brick" };
  return { label: say(item), icon: StepForward, tone: "text-ink-muted", dot: "bg-ink-faint" };
}
