/**
 * Where a person writes to a task, in the name of their person: while it works, the words reorient the work in
 * progress (steering); while it waits, they answer its question; otherwise they open the next turn of the same
 * thread. Enter sends, Shift+Enter goes to the line.
 */
import { ArrowUp, MessageSquareReply } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useState } from "react";
import { api, type Task } from "@/api";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";
import { cn } from "@/lib/utils";
import { useTaskChange } from "./parts";

/** What writing does, by where the task stands. */
const MODE = { working: "steer", waiting: "answer", ready: "continue", archived: "reopen" } as const;

export function TaskComposer({ task, onSent, className }: { task: Task; onSent?: () => void; className?: string }) {
  const t = useT();
  const notify = useNotify();
  const [text, setText] = useState("");
  const mode = MODE[task.state];
  const send = useTaskChange(
    task,
    () => api.directTask(task.id, text.trim()),
    (out) => {
      setText("");
      notify(t(out.steered ? "task-steered-notice" : "task-continued-notice"));
      onSent?.();
    },
  );
  if (!useCan("tasks:write")) return null;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (text.trim() && !send.isPending) send.mutate();
  }
  function keys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  }

  return (
    <form onSubmit={submit} className={cn("grid w-full gap-1.5", className)}>
      <FormError error={send.error} />
      <div className="flex items-end gap-2 rounded-2xl border border-rule-strong bg-paper-raised p-1.5 focus-within:border-ink">
        <Textarea
          aria-label={t(`task-composer-${mode}`)}
          placeholder={t(`task-composer-${mode}`)}
          value={text}
          rows={1}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={keys}
          className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 focus-visible:outline-none"
        />
        <Button
          type="submit"
          size="icon"
          aria-label={t("task-send")}
          disabled={!text.trim() || send.isPending}
          className="shrink-0 rounded-full"
        >
          <ArrowUp />
        </Button>
      </div>
      <p className="px-1 text-micro text-ink-muted">{t(`task-composer-${mode}-hint`)}</p>
    </form>
  );
}

/** On the task's page, writing to it is an action: a button that opens the composer in a dialog. */
export function WriteToTask({ task }: { task: Task }) {
  const t = useT();
  if (!useCan("tasks:write")) return null;
  const mode = MODE[task.state];
  return (
    <FormDialog
      trigger={
        <Button variant={mode === "answer" ? "default" : "outline"}>
          <MessageSquareReply /> {t(`task-write-${mode}`)}
        </Button>
      }
      title={t(`task-write-${mode}-title`)}
      description={task.question ?? undefined}
    >
      {(close) => <TaskComposer task={task} onSent={close} />}
    </FormDialog>
  );
}
