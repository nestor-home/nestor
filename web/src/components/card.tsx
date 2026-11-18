import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * What leads a card or a row: its mark, then its name in medium weight and one muted line, and what it says of
 * itself at the end of the line (a state, an owner, an arrow). The words take what is left and break; the mark
 * and the aside keep their size. `children` go under the words: more about it, then what one can do (a button).
 */
export function CardHead({
  mark,
  title,
  line,
  aside,
  children,
  className,
}: {
  mark?: ReactNode;
  title: ReactNode;
  line?: ReactNode;
  aside?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("flex min-w-0 flex-wrap items-start gap-x-3.5 gap-y-2", className)}>
      {mark}
      {/* the words keep at least 12rem: in a narrower card the aside goes under them rather than crush them */}
      <span className="grid min-w-0 flex-1 basis-48 gap-0.5">
        <span className="title-item text-ink">{title}</span>
        {line ? <span className="text-body text-ink-muted">{line}</span> : null}
        {children ? <span className="mt-2 grid justify-items-start gap-3">{children}</span> : null}
      </span>
      {aside ? <span className="ml-auto flex max-w-full items-center gap-2.5 self-center">{aside}</span> : null}
    </span>
  );
}

/**
 * A card that stands for a thing, in a grid of its kind: its marks across the top with what it says of itself at
 * the other end, its title in the display face, one muted line, and a foot (its state, when it was used).
 */
export function TileCard({
  marks,
  aside,
  title,
  line,
  foot,
}: {
  marks: ReactNode;
  aside?: ReactNode;
  title: ReactNode;
  line?: ReactNode;
  foot?: ReactNode;
}) {
  return (
    <>
      <span className="block min-w-0 flex-1">
        <span className="block title-card text-ink">{title}</span>
        {line ? <span className="mt-1.5 block text-body text-ink-muted">{line}</span> : null}
      </span>
      {/* read after its title (a card's name is its title first), drawn above it */}
      <span className="order-first flex w-full items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-1.5">{marks}</span>
        {aside ? <span className="flex shrink-0 items-center gap-2.5">{aside}</span> : null}
      </span>
      {foot ? (
        <span className="mt-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-rule pt-3 text-meta text-ink-muted">
          {foot}
        </span>
      ) : null}
    </>
  );
}

/** The class of a card that opens, laid out as a `TileCard`. */
export const TILE_CARD = "group surface flex h-full w-full flex-col gap-4 p-5 text-left";

/** The arrow of a card or a row that leads somewhere, darker on hover (the card is the `group`). */
export function OpenArrow({ className }: { className?: string }) {
  return (
    <ArrowRight
      className={cn("size-4 shrink-0 text-ink-faint transition-colors group-hover:text-ink", className)}
      aria-hidden="true"
    />
  );
}

/** The way to see all of what a section shows a few of, in its `aside`. */
export function MoreLink({ children, onClick, ...link }: LinkProps & { children: string; onClick?: () => void }) {
  return (
    <Link
      {...link}
      onClick={onClick}
      className="-mx-2 inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-body whitespace-nowrap text-ink-muted transition-colors hover:bg-paper-sunken hover:text-ink"
    >
      {children} <ArrowRight className="size-3.5" aria-hidden="true" />
    </Link>
  );
}
