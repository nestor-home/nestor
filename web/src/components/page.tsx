import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Dither } from "./dither";

/**
 * A screen's heading: breadcrumbs when the screen is deep, the serif title, a sentence only when
 * it tells something needed, and the signature dithered rule fading in from the right.
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
    <header className="relative mb-10">
      {crumbs}
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 pb-6">
        <div className="min-w-0 max-w-2xl">
          <h1 className="text-[1.9rem] leading-[1.05] font-normal [overflow-wrap:anywhere] text-ink sm:text-[2.4rem]">
            {title}
          </h1>
          {meta ? <div className="mt-3">{meta}</div> : null}
          {children ? (
            <p className="mt-3 text-[0.95rem] leading-relaxed text-pretty text-ink-muted">{children}</p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <div className="relative h-3">
        <div className="absolute inset-x-0 top-0 h-px bg-rule" />
        <Dither shape="ramp-right" from={0} to={0.55} className="absolute top-px right-0 h-2.5 w-2/5 text-ink/70" />
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
    <section aria-labelledby={headingId} className={cn("mb-12", className)}>
      <div className="mb-4 flex items-end justify-between gap-4 border-b border-rule pb-2">
        <h2 id={headingId} className="flex items-baseline gap-3 text-[1.3rem] font-normal text-ink">
          {title}
          {count !== undefined ? (
            <span className="font-mono text-xs font-normal text-ink-faint tabular">{count}</span>
          ) : null}
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
