import { Link, type LinkProps } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { Plus, Users } from "lucide-react";
import type { ReactNode } from "react";
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
  alert: "bg-paper-sunken text-kind-alert",
} as const;

export type TileTone = keyof typeof TILE;

/** The three tile sizes: `sm` in a row of a list, `md` on a card, `lg` at the head of a page or a sheet. */
const TILE_SIZE = { sm: "size-9 rounded-lg", md: "size-10 rounded-xl", lg: "size-12 rounded-xl" } as const;

export type TileSize = keyof typeof TILE_SIZE;

function Tile({
  tone = "ink",
  size = "md",
  className,
  children,
}: {
  tone?: TileTone;
  size?: TileSize;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("grid shrink-0 place-items-center [&>svg]:size-1/2", TILE_SIZE[size], TILE[tone], className)}
    >
      {children}
    </span>
  );
}

type TileProps = { tone?: TileTone; size?: TileSize; className?: string };

/** An icon on its tinted tile: what kind of thing a card is, read before its words. */
export function IconTile({ icon: Icon, ...tile }: TileProps & { icon: LucideIcon }) {
  return (
    <Tile {...tile}>
      <Icon />
    </Tile>
  );
}

/** A service's or a channel's logo on its tile, from the kind the API names: what leads every card of a
 * service or an account. */
export function ServiceTile({ kind, ...tile }: TileProps & { kind: string }) {
  return (
    <Tile {...tile}>
      <KindMark kind={kind} label={false} />
    </Tile>
  );
}

/** A brand's logo on its tile, when the code knows the brand itself. */
export function BrandTile({ brand, ...tile }: TileProps & { brand: BrandSlug }) {
  return (
    <Tile {...tile}>
      <BrandMark brand={brand} label={false} />
    </Tile>
  );
}

/** The avatar's sizes, its initials always 2/5 of it: from beside a word (`xs`) to the head of a page (`2xl`). */
const AVATAR_SIZE = {
  xs: "text-[0.5rem]",
  sm: "text-[0.6rem]",
  md: "text-[0.7rem]",
  lg: "text-[1rem]",
  xl: "text-[1.2rem]",
  "2xl": "text-[1.4rem] sm:text-[1.6rem]",
} as const;

export type AvatarSize = keyof typeof AVATAR_SIZE;

const HUES = 6;

/** The same person always wears the same tint, wherever they appear. */
function hueOf(name: string): number {
  let sum = 0;
  for (const letter of name.trim().toLowerCase()) sum = (sum * 31 + (letter.codePointAt(0) ?? 0)) % 997;
  return sum % HUES;
}

/** One or two initials: the first name's, and the last word's when there is one. */
function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0]?.charAt(0) ?? "";
  const last = words.length > 1 ? (words.at(-1)?.charAt(0) ?? "") : "";
  return (first + last).toUpperCase();
}

/**
 * A person: their initials on a quiet tint that is theirs. `away`, it fades to a plain outline. `lit` keeps its
 * daylight colours where the scene around it sets its own (a lit room at night).
 */
export function Avatar({
  name,
  away,
  lit,
  size = "md",
  className,
}: {
  name: string;
  away?: boolean;
  lit?: boolean;
  size?: AvatarSize;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      data-hue={hueOf(name)}
      data-away={away || undefined}
      data-lit={lit || undefined}
      className={cn("avatar", AVATAR_SIZE[size], className)}
    >
      {initialsOf(name)}
    </span>
  );
}

/** Whose something is, as a mark: the person's avatar, or the household's when it is everyone's. */
export function OwnerMark({
  owner,
  size = "md",
  className,
}: {
  owner: PersonRef | null;
  size?: AvatarSize;
  className?: string;
}) {
  if (owner) return <Avatar name={owner.name} size={size} className={className} />;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-[2.5em] shrink-0 place-items-center rounded-full bg-paper-sunken text-ink-muted",
        AVATAR_SIZE[size],
        className,
      )}
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
