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

/** Something to know before going on, boxed and announced: what went wrong, or what to watch out for. */
export function Notice({
  tone = "error",
  children,
  className,
}: {
  tone?: "error" | "attention";
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md border px-4 py-3 text-sm text-ink",
        tone === "error" ? "border-brick/40 bg-brick-soft/40" : "border-amber/40 bg-amber-soft/40",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A request that failed, in the words of the API, with a way to try again. */
export function Failure({ error, retry, className }: { error: unknown; retry?: () => void; className?: string }) {
  return (
    <Notice className={className}>
      <p>{messageOf(error)}</p>
      {retry ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={retry}>
          <RotateCw /> {tr("action-retry")}
        </Button>
      ) : null}
    </Notice>
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
