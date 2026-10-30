import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { STATUS_ICON } from "@/lib/icons";
import { cn } from "@/lib/utils";

export type StatusTone = "ok" | "attention" | "error" | "idle" | "accent" | "pending";

const TONE: Record<StatusTone, string> = {
  ok: "text-sage",
  attention: "text-amber",
  error: "text-brick",
  idle: "text-ink-muted",
  accent: "text-ember",
  pending: "text-amber",
};

const ICON: Record<StatusTone, LucideIcon | null> = {
  ok: STATUS_ICON.ok,
  attention: STATUS_ICON.attention,
  error: STATUS_ICON.error,
  idle: STATUS_ICON.idle,
  pending: STATUS_ICON.pending,
  accent: null, // the live dot
};

/** A status as an icon and a word in mono, coloured by tone; the word always says it. */
export function Status({ tone, children, className }: { tone: StatusTone; children: ReactNode; className?: string }) {
  const Icon = ICON[tone];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[0.85rem] whitespace-nowrap", TONE[tone], className)}>
      {Icon ? (
        <Icon className="size-3.5" aria-hidden="true" />
      ) : (
        <span aria-hidden="true" className="live-dot inline-block size-1.5 rounded-full bg-current" />
      )}
      {children}
    </span>
  );
}

/** A mono chip for data: rooms, channels, capabilities, tool names. */
export function Tag({
  children,
  className,
  tone,
  icon: Icon,
}: {
  children: ReactNode;
  className?: string;
  tone?: "accent" | "attention" | "error";
  icon?: LucideIcon;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border border-rule px-1.5 py-px text-[0.85rem] leading-4 text-ink-muted",
        tone === "accent" && "border-ember/40 text-ember",
        tone === "attention" && "border-amber/50 text-amber",
        tone === "error" && "border-brick/50 text-brick",
        className,
      )}
    >
      {Icon ? <Icon className="size-3" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm border border-rule-strong px-1 font-mono text-[0.65rem] leading-none text-ink-muted">
      {children}
    </kbd>
  );
}
