import type { LucideIcon } from "lucide-react";
import {
  BellRing,
  Check,
  CircleAlert,
  CircleHelp,
  CircleSlash,
  CornerDownRight,
  Inbox,
  Megaphone,
  MessageSquare,
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
  if (is(item, "taskInstructed"))
    return { label: tr("step-task-instructed"), icon: MessageSquare, tone: "text-kind-task", dot: "bg-kind-task" };
  if (is(item, "taskSteered"))
    return { label: tr("step-task-steered"), icon: CornerDownRight, tone: "text-kind-task", dot: "bg-kind-task" };
  if (is(item, "taskProgressed"))
    return { label: tr("step-task-progressed"), icon: StepForward, tone: "text-ink-muted", dot: "bg-ink-faint" };
  if (is(item, "taskEnded")) {
    const status = item.message.args.status;
    if (status === "failed") return { label: tr("step-task-failed"), icon: X, tone: "text-brick", dot: "bg-brick" };
    if (status === "stopped")
      return { label: tr("step-task-stopped"), icon: X, tone: "text-ink-muted", dot: "bg-ink-faint" };
    if (status === "asked")
      return { label: tr("step-task-asked"), icon: CircleHelp, tone: "text-amber", dot: "bg-amber" };
    return { label: tr("step-task-completed"), icon: Check, tone: "text-sage", dot: "bg-sage" };
  }
  if (is(item, "taskDelivered"))
    return { label: tr("step-task-delivered"), icon: Send, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "taskReminded"))
    return { label: tr("step-task-reminded"), icon: BellRing, tone: "text-amber", dot: "bg-amber" };
  if (is(item, "alertCreated"))
    return { label: tr("step-alert-created"), icon: Plus, tone: "text-kind-alert", dot: "bg-kind-alert" };
  if (is(item, "alertRang"))
    return { label: tr("step-alert-rang"), icon: Inbox, tone: "text-kind-alert", dot: "bg-kind-alert" };
  if (is(item, "considered"))
    return { label: tr("step-considered"), icon: Megaphone, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "delivered") && followUp)
    return { label: tr("step-follow-up"), icon: BellRing, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "delivered"))
    return item.channels.some((c) => SPOKEN.has(c))
      ? { label: tr("step-delivered-spoken"), icon: Volume2, tone: "text-ember", dot: "bg-ember" }
      : { label: tr("step-delivered-written"), icon: Send, tone: "text-ember", dot: "bg-ember" };
  if (is(item, "withheld"))
    return { label: tr("step-withheld"), icon: CircleSlash, tone: "text-ink-muted", dot: "bg-ink-faint" };
  if (is(item, "deliveryFailed"))
    return { label: tr("step-delivery-failed"), icon: CircleAlert, tone: "text-brick", dot: "bg-brick" };
  return { label: say(item), icon: StepForward, tone: "text-ink-muted", dot: "bg-ink-faint" };
}
