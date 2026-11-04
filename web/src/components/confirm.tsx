import { type ReactElement, type ReactNode, useState } from "react";
import { messageOf } from "@/api";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { tr } from "@/i18n/runtime";

/**
 * An action behind a confirmation, destructive unless `tone` says otherwise: the dialog stays open while the action runs and shows
 * its failure, so nothing is lost silently. It opens from its `trigger`, or from `open` when another
 * dialog hands over to it (`onOpenChange` hears it close).
 */
export function Confirm({
  trigger,
  open: shown,
  onOpenChange,
  title,
  children,
  confirm,
  onConfirm,
  tone = "destructive",
}: {
  trigger?: ReactElement;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  children: ReactNode;
  confirm: string;
  onConfirm: () => Promise<unknown>;
  tone?: "destructive" | "accent";
}) {
  const [own, setOwn] = useState(false);
  const open = shown ?? own;
  const setOpen = (next: boolean) => {
    setOwn(next);
    onOpenChange?.(next);
  };
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run() {
    setPending(true);
    setError(null);
    try {
      await onConfirm();
      setOpen(false);
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        setOpen(next);
        if (!next) setError(null);
      }}
    >
      {trigger ? <AlertDialogTrigger render={trigger} /> : null}
      <AlertDialogContent className="max-w-md! border border-rule bg-paper-raised">
        <AlertDialogHeader>
          <AlertDialogTitle className="font-serif text-xl font-normal">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-ink-muted">{children}</AlertDialogDescription>
        </AlertDialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-brick">
            {messageOf(error)}
          </p>
        ) : null}
        <AlertDialogFooter className="bg-paper-sunken/60">
          <AlertDialogCancel disabled={pending}>{tr("action-cancel")}</AlertDialogCancel>
          <Button variant={tone} onClick={run} disabled={pending}>
            {pending ? "…" : confirm}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
