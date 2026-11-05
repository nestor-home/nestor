import { type ReactNode, useEffect, useRef } from "react";
import { Dither } from "@/components/dither";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

/**
 * A guided flow in steps (recording a voice): Nestor on a band of breathing texture, the step's
 * title on plain paper below, what to do in a body that scrolls, the way on in a footer that stays.
 * The whole screen on a phone, a centred dialog elsewhere. When `step` changes, focus goes to the
 * new title, so a keyboard or a screen reader starts the step from its top.
 */
export function GuidedDialog({
  open,
  onOpenChange,
  stage,
  title,
  step,
  description,
  footer,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stage: ReactNode; // what stands on the band: Nestor
  title: string;
  step?: string;
  description: string; // for screen readers: what the dialog is about
  footer?: ReactNode;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const shown = useRef(step);
  useEffect(() => {
    if (shown.current === step) return;
    shown.current = step;
    heading.current?.focus();
  }, [step]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg max-sm:h-[100dvh] max-sm:max-h-none max-sm:max-w-none max-sm:rounded-none max-sm:border-0">
        <div className="relative flex shrink-0 items-center justify-center overflow-hidden bg-paper-sunken pt-[env(safe-area-inset-top)] max-sm:min-h-[38dvh]">
          <Dither shape="horizon" from={0} to={0.7} dot={3} animated className="absolute inset-0 text-ink/15" />
          <div className="relative py-6">{stage}</div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <div className="px-6 pt-5 text-center">
            <DialogTitle
              ref={heading}
              tabIndex={-1}
              className="font-serif text-2xl leading-tight font-normal text-balance [overflow-wrap:anywhere] text-ink outline-none"
            >
              {title}
            </DialogTitle>
            <DialogDescription className="sr-only">{description}</DialogDescription>
          </div>
          <div className="grid gap-5 px-6 pt-4 pb-6">{children}</div>
        </div>
        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-rule bg-paper-sunken/60 px-6 py-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
            {footer}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
