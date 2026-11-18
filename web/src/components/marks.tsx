import { Link, type LinkProps } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { Plus, Users } from "lucide-react";
import type { PersonRef } from "@/api";
import { BrandMark, type BrandSlug, KindMark } from "@/lib/brands";
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

const TILE_BOX = "grid size-10 shrink-0 place-items-center rounded-xl bg-paper-sunken text-ink";

/** A service's or a channel's logo on its tile, from the kind the API names: what leads every card of a
 * service or an account. */
export function ServiceTile({ kind, className }: { kind: string; className?: string }) {
  return (
    <span aria-hidden="true" className={cn(TILE_BOX, className)}>
      <KindMark kind={kind} label={false} className="size-1/2" />
    </span>
  );
}

/** A brand's logo on its tile, when the code knows the brand itself. */
export function BrandTile({ brand, className }: { brand: BrandSlug; className?: string }) {
  return (
    <span aria-hidden="true" className={cn(TILE_BOX, className)}>
      <BrandMark brand={brand} label={false} className="size-1/2" />
    </span>
  );
}

/** Whose something is, as a mark: the person's pebble, or the household's when it is everyone's. */
export function OwnerMark({ owner, className }: { owner: PersonRef | null; className?: string }) {
  if (owner) return <Pebble name={owner.name} className={className} />;
  return (
    <span
      aria-hidden="true"
      className={cn("grid size-7 shrink-0 place-items-center rounded-full bg-paper-sunken text-ink-muted", className)}
    >
      <Users className="size-1/2" />
    </span>
  );
}

/** The last card of a list of things one can add: the way to add one, where one is looking at them. */
export function AddCard({ link, children, className }: { link: LinkProps; children: string; className?: string }) {
  return (
    <Link
      {...link}
      className={cn(
        "surface-quiet flex h-full min-h-24 items-center justify-center gap-2 px-4 py-5 text-[0.95rem] font-medium text-ink-muted transition-colors hover:border-ink-faint hover:bg-paper-raised hover:text-ink",
        className,
      )}
    >
      <Plus className="size-4.5" aria-hidden="true" />
      {children}
    </Link>
  );
}
