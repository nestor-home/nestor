import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Dither } from "@/components/dither";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/**
 * An update, Nestor's or a satellite's: a band of breathing texture with who updates standing on it,
 * the title and the versions on plain paper below, what changes in a body that scrolls, and the
 * action in a footer that stays. `tone` tells them apart at a glance: ember for Nestor, ink for a
 * device.
 */
export function UpdateDialog({
  open,
  onOpenChange,
  tone,
  mark,
  title,
  description,
  running,
  latest,
  aside,
  footer,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tone: "ember" | "ink";
  mark: ReactNode;
  title: string;
  description: string; // for screen readers: what the dialog is about
  running: string;
  latest: string;
  aside?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-xl">
        <div
          className={cn(
            "relative flex h-36 shrink-0 items-end justify-center overflow-hidden",
            tone === "ember" ? "bg-ember-soft/50" : "bg-paper-sunken",
          )}
        >
          <Dither
            shape="horizon"
            from={0}
            to={0.75}
            dot={3}
            animated
            className={cn("absolute inset-0", tone === "ember" ? "text-ember/45" : "text-ink/20")}
          />
          <div className="relative">{mark}</div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-6 pt-5 text-center">
            <DialogTitle className="font-serif text-2xl leading-tight font-normal text-balance text-ink">
              {title}
            </DialogTitle>
            <DialogDescription className="sr-only">{description}</DialogDescription>
            <p className="mt-2 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 font-mono text-sm text-ink-muted">
              <span>{running}</span>
              <ArrowRight className="size-3.5" aria-hidden="true" />
              <span className={tone === "ember" ? "text-ember" : "text-ink"}>{latest}</span>
              {aside ? <span className="font-sans">· {aside}</span> : null}
            </p>
          </div>
          <div className="grid gap-6 px-6 pt-6 pb-6">{children}</div>
        </div>
        {footer ? <div className="border-t border-rule bg-paper-sunken/60 px-6 py-4">{footer}</div> : null}
      </DialogContent>
    </Dialog>
  );
}
