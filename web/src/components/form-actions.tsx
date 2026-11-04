import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The actions that end a form, at the end of the line, with an optional `hint` before them. In a
 * dialog they become its footer, and stay in reach while the body scrolls (app.css,
 * `[data-slot="form-actions"]`).
 */
export function FormActions({
  hint,
  className,
  children,
}: {
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div data-slot="form-actions" className={cn("flex flex-wrap items-center justify-end gap-3", className)}>
      {hint ? <span className="mr-auto text-xs text-ink-muted">{hint}</span> : null}
      {children}
    </div>
  );
}
