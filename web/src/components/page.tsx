import { ArrowRight } from "lucide-react";
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
}: {
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  crumbs?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header className="mb-10 md:mb-14">
      {crumbs}
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 max-w-3xl">
          <h1 className="display-2 [overflow-wrap:anywhere] text-ink">{title}</h1>
          {meta ? (
            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">{meta}</p>
          ) : null}
          {children ? <p className="lede mt-4 max-w-2xl">{children}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

/** A titled part of a screen: a ruled header with the serif title, a count, and its own actions. */
export function Section({
  title,
  count,
  aside,
  children,
  className,
  id,
}: {
  title: string;
  count?: number;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const headingId = id ?? `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section aria-labelledby={headingId} className={cn("mb-14", className)}>
      <div className="mb-5 flex items-end justify-between gap-4">
        <h2 id={headingId} className="display-3 flex items-baseline gap-2.5 text-ink">
          {title}
          {count !== undefined ? <span className="font-sans text-sm text-ink-faint tabular">{count}</span> : null}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** The arrow that ends a linked row, shown on wider screens, darker on hover (the row is the `group`). */
export function RowArrow() {
  return <ArrowRight className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block" aria-hidden="true" />;
}

/** The opening sentence of a detail screen, in the serif at reading size. */
export function Lead({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-2xl font-serif text-[1.2rem] leading-relaxed text-pretty [font-variation-settings:'opsz'_20]">
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
    <dl
      className={cn(
        "grid gap-y-2.5 text-sm",
        narrow ? "grid-cols-[7rem_1fr] gap-x-4 gap-y-1.5" : "max-w-2xl grid-cols-1 gap-x-6 sm:grid-cols-[10rem_1fr]",
        className,
      )}
    >
      {children}
    </dl>
  );
}

/** One fact of `Facts`: its caption, then its value. */
export function Fact({ term, children, className }: { term: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className="contents">
      <dt className="label-mono pt-0.5">{term}</dt>
      <dd className={className}>{children}</dd>
    </div>
  );
}

/** Rows of one kind on a hairline surface, a rule between each: accounts, tasks, satellites… */
export function RowList({
  children,
  ordered = false,
  className,
}: {
  children: ReactNode;
  ordered?: boolean;
  className?: string;
}) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={cn("divide-y divide-rule rounded-md border border-rule bg-paper-raised", className)}>
      {children}
    </Tag>
  );
}

/**
 * A hairline-bordered surface. `marked` adds the corner ticks of the signature, for the one or two
 * surfaces of a screen that matter most.
 */
export function Panel({
  children,
  className,
  marked = false,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  marked?: boolean;
  as?: "div" | "li" | "section" | "article";
}) {
  return (
    <Tag
      className={cn("relative rounded-md border border-rule bg-paper-raised p-5", marked && "corner-marks", className)}
    >
      {children}
    </Tag>
  );
}
