import { type ReactElement, type ReactNode, useState } from "react";
import { FormError } from "@/components/states";
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
import { useOpenState } from "@/hooks/use-open-state";
import { tr } from "@/i18n/runtime";

/** The frame every confirmation shares: its title, what it means, any detail, then cancel and the action. */
export function ConfirmFrame({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  details,
  cancel = tr("action-cancel"),
  busy = false,
  action,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: ReactElement;
  title: string;
  description: ReactNode;
  details?: ReactNode;
  cancel?: string;
  busy?: boolean;
  action: ReactNode;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      {trigger ? <AlertDialogTrigger render={trigger} /> : null}
      <AlertDialogContent className="max-w-md! border border-rule bg-paper-raised">
        <AlertDialogHeader>
          <AlertDialogTitle className="font-serif text-xl font-normal">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-ink-muted">{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {details}
        <AlertDialogFooter className="bg-paper-sunken/60">
          <AlertDialogCancel disabled={busy}>{cancel}</AlertDialogCancel>
          {action}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

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
  cancel,
  onConfirm,
  tone = "destructive",
}: {
  trigger?: ReactElement;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  children: ReactNode;
  confirm: string;
  cancel?: string;
  onConfirm: () => Promise<unknown>;
  tone?: "destructive" | "accent";
}) {
  const [open, setOpen] = useOpenState(shown, onOpenChange);
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
    <ConfirmFrame
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        setOpen(next);
        if (!next) setError(null);
      }}
      trigger={trigger}
      title={title}
      description={children}
      details={<FormError error={error} />}
      cancel={cancel}
      busy={pending}
      action={
        <Button variant={tone} onClick={run} disabled={pending}>
          {pending ? "…" : confirm}
        </Button>
      }
    />
  );
}
