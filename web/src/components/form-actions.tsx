import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The actions that end a form: together at the end of the line, an optional `hint` before them. They are part
 * of the form and scroll with it; an overlay that holds actions in reach has its own foot for them
 * (`SheetPanel`'s `actions`, a dialog's footer).
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
    <div className={cn("flex flex-wrap items-center justify-end gap-x-4 gap-y-2.5", className)}>
      {/* the hint keeps a readable width: where it cannot sit beside the actions, it takes its own line above them */}
      {hint ? <span className="min-w-48 flex-1 text-meta text-ink-muted">{hint}</span> : null}
      <span className="flex flex-wrap items-center justify-end gap-3">{children}</span>
    </div>
  );
}
