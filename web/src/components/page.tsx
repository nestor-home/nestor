import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A screen's heading: breadcrumbs when the screen is deep, the serif title at the site's scale, a
 * sentence only when it tells something needed.
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
          {meta ? <div className="mt-3">{meta}</div> : null}
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
