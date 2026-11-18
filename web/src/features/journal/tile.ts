import type { LucideIcon } from "lucide-react";
import type { JournalItem, Kind } from "@/api";
import type { TileTone } from "@/components/marks";
import { kindStyle } from "@/lib/icons";

const TONE: Partial<Record<Kind, TileTone>> = { delivery: "ember", task: "task", watch: "watch", memory: "sage" };

/** The tile that leads an event: its kind's icon, in its kind's colour, brick when something went wrong. */
export function tileOf(item: Pick<JournalItem, "kind" | "tone">): { icon: LucideIcon; tone: TileTone } {
  return { icon: kindStyle(item.kind).icon, tone: item.tone === "warning" ? "brick" : (TONE[item.kind] ?? "ink") };
}
