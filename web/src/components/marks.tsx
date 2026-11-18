import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const TILE = {
  ink: "bg-paper-sunken text-ink",
  ember: "bg-ember-soft text-ember",
  sage: "bg-sage-soft text-sage",
  amber: "bg-amber-soft text-amber",
  brick: "bg-brick-soft text-brick",
  task: "bg-paper-sunken text-kind-task",
  watch: "bg-paper-sunken text-kind-watch",
} as const;

export type TileTone = keyof typeof TILE;

/** An icon on its tinted tile: what kind of thing a card is, read before its words. */
export function IconTile({
  icon: Icon,
  tone = "ink",
  className,
}: {
  icon: LucideIcon;
  tone?: TileTone;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("grid size-10 shrink-0 place-items-center rounded-xl", TILE[tone], className)}
    >
      <Icon className="size-5" />
    </span>
  );
}

/** A person as the film draws them: an ink pebble with an ember scarf, their initial on it. */
export function Pebble({ name, away, className }: { name: string; away?: boolean; className?: string }) {
  return (
    <span aria-hidden="true" data-away={away || undefined} className={cn("pebble size-7 text-[0.72rem]", className)}>
      {name.trim().charAt(0).toUpperCase()}
    </span>
  );
}
