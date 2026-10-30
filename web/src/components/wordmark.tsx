import { cn } from "@/lib/utils";

/**
 * The logo slot. Until there is a logo, the wordmark: "nestor" in the display serif, followed by
 * an ember block cursor; `compact` keeps the initial and the cursor (the collapsed sidebar).
 * Replace the inside of this component and nothing else changes.
 */
export function Wordmark({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-baseline gap-[0.12em] font-serif leading-none text-ink", className)}>
      <span className="font-medium tracking-[-0.02em] [font-variation-settings:'SOFT'_100,'opsz'_72]">
        {compact ? "n" : "nestor"}
      </span>
      <span aria-hidden="true" className="inline-block h-[0.62em] w-[0.36em] translate-y-[0.02em] bg-ember" />
    </span>
  );
}
