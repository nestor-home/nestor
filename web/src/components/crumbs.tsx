import { Link, type LinkProps } from "@tanstack/react-router";
import { Fragment } from "react";
import { tr } from "@/i18n/runtime";

export interface Crumb {
  label: string;
  link?: LinkProps;
}

/** Where a deep screen sits: each level a link, the current one plain. */
export function Crumbs({ trail }: { trail: Crumb[] }) {
  return (
    <nav aria-label={tr("breadcrumbs")} className="mb-5 font-mono text-xs text-ink-muted">
      <ol className="flex flex-wrap items-center gap-x-2">
        {trail.map((crumb, i) => (
          <Fragment key={crumb.label}>
            {i > 0 ? (
              <li aria-hidden="true" className="text-ink-faint">
                /
              </li>
            ) : null}
            <li>
              {crumb.link && i < trail.length - 1 ? (
                <Link {...crumb.link} className="hover:text-ink">
                  {crumb.label}
                </Link>
              ) : (
                <span aria-current="page" className="text-ink">
                  {crumb.label}
                </span>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
