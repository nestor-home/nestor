import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A screen's heading: breadcrumbs when the screen is deep, the serif title at the site's scale, its
 * `meta` on one muted line (status, ids, where), a sentence only when it tells something needed.
 */
export function PageHeader({
  title,
  children,
  actions,
  crumbs,
  meta,
  mark,
}: {
  title: ReactNode;
  /** what the page is about, drawn before its title: a person's pebble, a service's tile */
  mark?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  crumbs?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header className="mb-8">
      {crumbs}
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 max-w-3xl">
          <h1 className="display-2 flex items-center gap-4 text-ink">
            {mark}
            <span className="min-w-0">{title}</span>
          </h1>
          {meta ? (
            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-muted">{meta}</p>
          ) : null}
          {children ? <p className="mt-2 max-w-[60ch] text-lead text-ink-muted">{children}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

/** A titled part of a screen (`level` 3: of a sheet or of a card): its title, how many it holds, and its own
 * actions. */
export function Section({
  title,
  count,
  aside,
  children,
  className,
  id,
  level = 2,
}: {
  title: string;
  count?: number;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  level?: 2 | 3;
}) {
  const headingId = id ?? `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={headingId} className={cn("min-w-0", className)}>
      <div className={cn("flex items-baseline justify-between gap-4", level === 2 ? "mb-4" : "mb-3")}>
        <Heading
          id={headingId}
          className={cn("flex items-baseline gap-2.5 text-ink", level === 2 ? "display-3" : "title-sub")}
        >
          {title}
          {count ? <Count n={count} /> : null}
        </Heading>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** How many of something, on its small ink pill: beside a title, on a rail entry, on a filter. `ember` when it
 * waits on someone, `brick` when it counts problems. */
export function Count({
  n,
  tone = "ink",
  className,
}: {
  n: number;
  tone?: "ink" | "ember" | "brick";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-grid h-5 min-w-5 place-items-center rounded-full px-1.5 font-sans text-micro leading-none font-semibold tabular",
        tone === "ink" && "bg-ink text-paper",
        tone === "ember" && "bg-ember text-on-ember",
        tone === "brick" && "bg-brick-soft text-brick",
        className,
      )}
    >
      {n}
    </span>
  );
}

/** The opening sentence of a detail screen, in the serif at reading size. */
export function Lead({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-2xl font-serif text-heading leading-relaxed text-pretty [font-variation-settings:'opsz'_20]">
      {children}
    </p>
  );
}

/** A detail screen's two columns on wide screens: the story, then a narrow aside. */
export function WithAside({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] [&>*]:min-w-0">{children}</div>;
}

/** Facts about one thing, a mono caption before each value; `narrow` in a sheet, where the captions are short. */
export function Facts({
  children,
  narrow = false,
  className,
}: {
  children: ReactNode;
  narrow?: boolean;
  className?: string;
}) {
  return (
    <div className="@container min-w-0">
      <dl
        className={cn(
          "grid gap-y-2.5 text-meta",
          // in a narrow place (an aside, a sheet on a phone) each caption sits above its value
          narrow
            ? "grid-cols-1 gap-x-4 gap-y-1.5 @[19rem]:grid-cols-[7rem_1fr] [&_dd]:mb-1.5 @[19rem]:[&_dd]:mb-0"
            : "max-w-2xl grid-cols-1 gap-x-6 @[30rem]:grid-cols-[10rem_1fr]",
          className,
        )}
      >
        {children}
      </dl>
    </div>
  );
}

/** One fact of `Facts`: its caption, then its value. */
export function Fact({ term, children, className }: { term: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className="contents">
      <dt className="caption pt-0.5">{term}</dt>
      <dd className={cn("min-w-0", className)}>{children}</dd>
    </div>
  );
}

/** Rows of one kind on a raised surface, a rule between each: accounts, tasks, satellites… */
export function RowList({
  children,
  ordered = false,
  className,
  ...rest
}: {
  children: ReactNode;
  ordered?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={cn("surface divide-y divide-rule overflow-hidden", className)} {...rest}>
      {children}
    </Tag>
  );
}

/**
 * A raised surface. `marked` adds the corner ticks of the signature, for the one or two
 * surfaces of a screen that matter most.
 */
export function Panel({
  children,
  className,
  marked = false,
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  marked?: boolean;
  as?: "div" | "li" | "section" | "article" | "aside";
  "aria-label"?: string;
}) {
  return (
    <Tag className={cn("surface relative p-5", marked && "corner-marks", className)} {...rest}>
      {children}
    </Tag>
  );
}
