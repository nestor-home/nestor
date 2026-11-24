/**
 * What every place that shows a task shares: its state, a card's content, its steps, and what one can do to it
 * (rename, stop, archive). Kept apart from the thread and the task's page so that Today and Ongoing load little.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, CircleHelp, Pencil, Square, Workflow } from "lucide-react";
import { type FormEvent, useState } from "react";
import { api, keys, type Task, type TaskState, type TaskThread } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { Field } from "@/components/field";
import { FormActions } from "@/components/form-actions";
import { Avatar, IconTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { FormError } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";
import { KindName } from "@/lib/brands";
import { taskStateLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";
import { cn } from "@/lib/utils";

const TONE: Record<TaskState, StatusTone> = { working: "accent", waiting: "pending", ready: "ok", archived: "idle" };

export function TaskStateMark({ state }: { state: TaskState }) {
  return <Status tone={TONE[state]}>{taskStateLabel(state)}</Status>;
}

/** The question a task waits on, as it is read before anything else about it. */
export function Question({ text, className }: { text: string; className?: string }) {
  return (
    <span
      className={cn("flex items-start gap-2.5 rounded-xl bg-amber-soft px-3.5 py-2.5 text-body text-ink", className)}
    >
      <CircleHelp className="mt-0.5 size-4 shrink-0 text-amber" aria-hidden="true" />
      <span className="min-w-0 whitespace-pre-line">{text}</span>
    </span>
  );
}

/**
 * A task as a card's content: who does it and for whom, then where it stands. Waiting: its question; working: its
 * latest step and the thread that moves; otherwise its state and when it last moved.
 */
export function TaskCardBody({ task }: { task: Task }) {
  const t = useT();
  return (
    <>
      <CardHead
        mark={<IconTile icon={Workflow} tone="task" />}
        title={task.title}
        line={
          <span className="flex flex-wrap items-center gap-x-2.5">
            <KindName kind={task.executor} />
            <Ago iso={task.last_activity} />
            {task.turns > 1 ? <span>{t("task-turns", { count: task.turns })}</span> : null}
          </span>
        }
        aside={task.owner ? <Avatar name={task.owner.name} /> : null}
      />
      {task.state === "waiting" && task.question ? (
        <Question text={task.question} className="mt-3.5 [&>span:last-child]:line-clamp-3" />
      ) : task.state === "working" ? (
        <>
          <span className="mt-3.5 line-clamp-2 block text-body text-ink">{task.now ?? t("task-starting")}</span>
          <span className="thread mt-2.5 block" aria-hidden="true" />
        </>
      ) : null}
    </>
  );
}

/** What an executor reported as it went, oldest first; the last one glows while it works. */
export function Steps({ steps, live, className }: { steps: readonly string[]; live: boolean; className?: string }) {
  return (
    <ol className={className}>
      {steps.map((step, index) => {
        const last = index === steps.length - 1;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: steps are an append-only list of plain strings
          <li key={index} className="grid grid-cols-[1.25rem_1fr] gap-x-3">
            <span className="flex flex-col items-center" aria-hidden="true">
              <span
                className={cn("mt-1.5 size-2.5 rounded-full", last && live ? "live-dot bg-ember" : "bg-rule-strong")}
              />
              {last ? null : <span className="w-px flex-1 bg-rule" />}
            </span>
            <span className={cn("min-w-0 pb-3 text-body", last ? "text-ink" : "text-ink-muted")}>{step}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** A change to a task, with what follows it everywhere: the lists and the thread read again, a notice. */
export function useTaskChange<T>(task: Pick<Task, "id">, run: () => Promise<T>, onDone?: (result: T) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: keys.tasks });
      const thread = threadOf(result);
      if (thread) queryClient.setQueryData(keys.task(task.id), thread);
      onDone?.(result);
    },
  });
}

/** The thread a change answers with: the task itself, or under `task`. */
function threadOf(result: unknown): TaskThread | null {
  if (!result || typeof result !== "object") return null;
  if ("thread" in result) return result as TaskThread;
  if ("task" in result) return (result as { task: TaskThread }).task;
  return null;
}

/** Rename, stop and archive, each where it applies and for whoever may; `onArchived` once it is put away. */
export function TaskActions({ task, onArchived }: { task: Task; onArchived?: () => void }) {
  if (!useCan("tasks:write")) return null;
  return (
    <>
      <RenameTask task={task} />
      {task.state === "working" ? <StopTask task={task} /> : null}
      {task.state === "archived" ? null : <ArchiveTask task={task} onDone={onArchived} />}
    </>
  );
}

function RenameTask({ task }: { task: Task }) {
  const t = useT();
  return (
    <FormDialog
      trigger={
        <Button variant="outline">
          <Pencil /> {t("task-rename-action")}
        </Button>
      }
      title={t("task-rename-title")}
    >
      {(close) => <RenameForm task={task} onDone={close} />}
    </FormDialog>
  );
}

function RenameForm({ task, onDone }: { task: Task; onDone: () => void }) {
  const t = useT();
  const notify = useNotify();
  const [title, setTitle] = useState(task.title);
  const rename = useTaskChange(
    task,
    () => api.renameTask(task.id, title.trim()),
    () => {
      notify(t("task-renamed-notice"));
      onDone();
    },
  );
  function submit(event: FormEvent) {
    event.preventDefault();
    if (title.trim()) rename.mutate();
  }
  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field label={t("task-rename-label")} htmlFor="task-title">
        <Input id="task-title" autoFocus value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <FormError error={rename.error} />
      <FormActions>
        <Button type="submit" disabled={rename.isPending || !title.trim() || title.trim() === task.title}>
          {t("task-rename-save")}
        </Button>
      </FormActions>
    </form>
  );
}

function StopTask({ task }: { task: Task }) {
  const t = useT();
  const notify = useNotify();
  const stop = useTaskChange(
    task,
    () => api.stopTask(task.id),
    (out) => notify(t(out.confirmed ? "task-stopped-notice" : "task-stop-pending-notice")),
  );
  return (
    <Confirm
      trigger={
        <Button variant="outline">
          <Square /> {t("task-stop-action")}
        </Button>
      }
      title={t("task-stop-title")}
      confirm={t("task-stop")}
      onConfirm={() => stop.mutateAsync()}
    >
      {t("task-stop-description")}
    </Confirm>
  );
}

function ArchiveTask({ task, onDone }: { task: Task; onDone?: () => void }) {
  const t = useT();
  const notify = useNotify();
  const archive = useTaskChange(
    task,
    () => api.archiveTask(task.id),
    () => {
      notify(t("task-archived-notice"));
      onDone?.();
    },
  );
  return (
    <Confirm
      trigger={
        <Button variant="outline">
          <Archive /> {t("task-archive-action")}
        </Button>
      }
      title={t("task-archive-title")}
      confirm={t("task-archive")}
      onConfirm={() => archive.mutateAsync()}
    >
      {t("task-archive-description", { working: task.state === "working" ? "yes" : "no" })}
    </Confirm>
  );
}
