import type { LucideIcon } from "lucide-react";
import { type ReactElement, type ReactNode, useRef } from "react";
import { IconTile, type TileTone } from "@/components/marks";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useOpenState } from "@/hooks/use-open-state";

/**
 * The one rule for editing: a page shows content; creating or changing is an explicit action that
 * opens a form. A Dialog for a short, focused form; a Sheet from the right for a longer or
 * contextual one. `children` receives `close` to call once the form succeeded. Both open from their
 * `trigger`, or from `open` when the page decides (`onOpenChange` hears them close).
 */
export function FormDialog({
  trigger,
  title,
  description,
  children,
  wide = false,
  open: controlled,
  onOpenChange,
}: {
  trigger?: ReactElement;
  title: string;
  description?: ReactNode;
  children: (close: () => void) => ReactNode;
  wide?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useOpenState(controlled, onOpenChange);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger ? <DialogTrigger render={trigger} /> : null}
      <DialogContent className={wide ? "sm:max-w-xl" : "sm:max-w-md"}>
        <DialogHeader>
          <DialogTitle className="title-card font-normal">{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {open ? children(() => setOpen(false)) : null}
      </DialogContent>
    </Dialog>
  );
}

/**
 * What an overlay holds, kept while it closes: a page that opens a sheet for "the thing I clicked" drops that
 * thing the moment it closes, and the sheet would empty before it has left.
 */
function useKept(open: boolean, children: ReactNode): ReactNode {
  const kept = useRef(children);
  if (open) kept.current = children;
  return kept.current;
}

/** A sheet from the right, or the full screen from below on a phone: the frame of every sheet. */
export function SideSheet({
  open,
  onOpenChange,
  trigger,
  onClosed,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: ReactElement;
  /** Once it has finished closing: for a page that mounts it only while it shows. */
  onClosed?: () => void;
  children: ReactNode;
}) {
  const mobile = useIsMobile();
  const held = useKept(open, children);
  return (
    <Sheet open={open} onOpenChange={onOpenChange} onOpenChangeComplete={(now) => !now && onClosed?.()}>
      {trigger ? <SheetTrigger render={trigger} /> : null}
      <SheetContent
        side={mobile ? "bottom" : "right"}
        className={
          mobile
            ? "h-[100dvh] w-full overflow-y-auto overscroll-contain bg-paper pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
            : "w-full overflow-y-auto overscroll-contain bg-paper sm:max-w-xl"
        }
      >
        {held}
      </SheetContent>
    </Sheet>
  );
}

/** A short drawer from the bottom (filters on a phone): its title, then what it holds. */
export function BottomSheet({
  open,
  onOpenChange,
  trigger,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: ReactElement;
  title: string;
  children: ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger render={trigger} />
      <SheetContent
        side="bottom"
        className="max-h-[85dvh] overflow-y-auto overscroll-contain rounded-t-xl bg-paper pb-[env(safe-area-inset-bottom)]"
      >
        <SheetHeader className="border-b border-rule px-5 pt-5 pb-3">
          <SheetTitle className="title-card font-normal">{title}</SheetTitle>
        </SheetHeader>
        {children}
      </SheetContent>
    </Sheet>
  );
}

export function FormSheet({
  trigger,
  title,
  description,
  children,
  open: controlled,
  onOpenChange,
  onClosed,
}: {
  trigger?: ReactElement;
  title: string;
  description?: ReactNode;
  children: (close: () => void) => ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onClosed?: () => void;
}) {
  const [open, setOpen] = useOpenState(controlled, onOpenChange);
  return (
    <SideSheet open={open} onOpenChange={setOpen} trigger={trigger} onClosed={onClosed}>
      <SheetPanel title={title} description={description}>
        {open ? children(() => setOpen(false)) : null}
      </SheetPanel>
    </SideSheet>
  );
}

/**
 * What a side sheet holds when it opens one thing (a task, a room, a device): what kind of thing it is, its
 * title, its body, and its actions held at the foot while the body scrolls.
 */
export function SheetPanel({
  icon,
  tone,
  kind,
  title,
  description,
  children,
  actions,
}: {
  icon?: LucideIcon;
  tone?: TileTone;
  kind?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <>
      <SheetHeader className="gap-3 px-6 pt-8 pb-2">
        {kind ? (
          <span className="flex items-center gap-3 text-body font-medium text-ink-muted">
            {icon ? <IconTile icon={icon} tone={tone} size="sm" /> : null}
            {kind}
          </span>
        ) : null}
        <SheetTitle className="title-sheet font-normal">{title}</SheetTitle>
        <SheetDescription className={description ? "text-body text-ink-muted" : "sr-only"}>
          {description ?? kind ?? title}
        </SheetDescription>
      </SheetHeader>
      <div className="grid gap-7 px-6 pb-8">{children}</div>
      {actions ? (
        <div data-slot="sheet-actions" className="sticky bottom-0 mt-auto flex flex-wrap gap-2">
          {actions}
        </div>
      ) : null}
    </>
  );
}
