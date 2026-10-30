import { type ReactElement, type ReactNode, useState } from "react";
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

/**
 * The one rule for editing: a page shows content; creating or changing is an explicit action that
 * opens a form. A Dialog for a short, focused form; a Sheet from the right for a longer or
 * contextual one. `children` receives `close` to call once the form succeeded.
 */
export function FormDialog({
  trigger,
  title,
  description,
  children,
  wide = false,
}: {
  trigger: ReactElement;
  title: string;
  description?: ReactNode;
  children: (close: () => void) => ReactNode;
  wide?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger} />
      <DialogContent className={wide ? "sm:max-w-xl" : "sm:max-w-md"}>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl font-normal">{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {open ? children(() => setOpen(false)) : null}
      </DialogContent>
    </Dialog>
  );
}

export function FormSheet({
  trigger,
  title,
  description,
  children,
  open: controlled,
  onOpenChange,
}: {
  trigger?: ReactElement;
  title: string;
  description?: ReactNode;
  children: (close: () => void) => ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const mobile = useIsMobile();
  const [own, setOwn] = useState(false);
  const open = controlled ?? own;
  const setOpen = (next: boolean) => {
    setOwn(next);
    onOpenChange?.(next);
  };
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {trigger ? <SheetTrigger render={trigger} /> : null}
      <SheetContent
        side={mobile ? "bottom" : "right"}
        className={
          mobile
            ? "h-[100dvh] w-full overflow-y-auto overscroll-contain bg-paper pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
            : "w-full overflow-y-auto overscroll-contain bg-paper sm:max-w-xl"
        }
      >
        <SheetHeader className="border-b border-rule px-6 pt-6 pb-4">
          <SheetTitle className="font-serif text-2xl font-normal">{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <div className="px-6 pb-8">{open ? children(() => setOpen(false)) : null}</div>
      </SheetContent>
    </Sheet>
  );
}
