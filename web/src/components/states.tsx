import { RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { messageOf } from "@/api";
import { Button } from "@/components/ui/button";
import { tr } from "@/i18n/runtime";
import { cn } from "@/lib/utils";
import { AgentFigure } from "./agent-figure";

/** Nothing to show: the agent beside it, said plainly, with what would make something appear. */
export function Empty({
  children,
  hint,
  action,
  className,
}: {
  children: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-4 py-6", className)}>
      <AgentFigure state="idle" size="md" />
      <div className="min-w-0">
        <p className="text-[1.02rem] text-ink">{children}</p>
        {hint ? <p className="mt-1 max-w-xl text-ink-muted">{hint}</p> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </div>
  );
}

export function Failure({ error, retry, className }: { error: unknown; retry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("rounded-md border border-brick/40 bg-brick-soft/40 px-5 py-4", className)}>
      <p className="text-sm text-ink">{messageOf(error)}</p>
      {retry ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={retry}>
          <RotateCw /> {tr("action-retry")}
        </Button>
      ) : null}
    </div>
  );
}

/** Placeholder rows in the dithered texture while the data comes. */
export function Loading({ lines = 3, label }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="flex items-center gap-2">
        <AgentFigure state="thinking" size="sm" />
        <span className="sr-only">{label ?? tr("loading")}</span>
      </span>
      {Array.from({ length: lines }, (_, i) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders
          key={i}
          className="loading-row h-12 overflow-hidden rounded-md bg-paper-sunken/70"
        />
      ))}
    </div>
  );
}

/** Inline form error, announced. */
export function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-brick">
      {typeof error === "string" ? error : messageOf(error)}
    </p>
  );
}
