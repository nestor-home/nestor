/**
 * What every place that shows a task shares: its state, the card of one that runs, its steps, and the way to
 * stop it. Kept apart from the task's page so that Today and Ongoing do not load it.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Workflow, X } from "lucide-react";
import { api, keys, type Task, type TaskStatus } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { IconTile, Pebble } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { Status, type StatusTone } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { KindName } from "@/lib/brands";
import { taskStatusLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";
import { cn } from "@/lib/utils";

const TONE: Record<TaskStatus, StatusTone> = { running: "accent", completed: "ok", failed: "error", cancelled: "idle" };

export function TaskStatusMark({ status }: { status: TaskStatus }) {
  return <Status tone={TONE[status]}>{taskStatusLabel(status)}</Status>;
}

/** A task that runs, as a card's content: who does it and since when, its last step, and the thread that moves. */
export function RunningTask({ task }: { task: Task }) {
  const t = useT();
  return (
    <>
      <CardHead
        mark={<IconTile icon={Workflow} tone="task" />}
        title={task.title}
        line={
          <span className="flex flex-wrap items-center gap-x-2.5">
            <KindName kind={task.executor} />
            <span>
              {t("task-since")} <Ago iso={task.started_at} />
            </span>
          </span>
        }
        aside={task.requested_by ? <Pebble name={task.requested_by.name} /> : null}
      />
      <span className="mt-3.5 block text-body text-ink">{task.steps.at(-1) ?? t("home-task-starting")}</span>
      <span className="thread mt-2.5 block" aria-hidden="true" />
    </>
  );
}

/** What the executor reported as it went, oldest first; the last one glows while the task runs. */
export function Steps({ task, className }: { task: Task; className?: string }) {
  return (
    <ol className={className}>
      {task.steps.map((step, index) => {
        const last = index === task.steps.length - 1;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: steps are an append-only list of plain strings
          <li key={index} className="grid grid-cols-[1.25rem_1fr] gap-x-3">
            <span className="flex flex-col items-center" aria-hidden="true">
              <span
                className={cn(
                  "mt-1.5 size-2.5 rounded-full",
                  last && task.status === "running" ? "live-dot bg-ember" : "bg-rule-strong",
                )}
              />
              {last ? null : <span className="w-px flex-1 bg-rule" />}
            </span>
            <span className={cn("min-w-0 pb-3.5 text-body", last ? "text-ink" : "text-ink-muted")}>{step}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The way to stop a task that runs, behind its confirmation, for whoever may; `onDone` once it is stopped. */
export function CancelTask({ task, onDone }: { task: Task; onDone?: () => void }) {
  const t = useT();
  const allowed = useCan("tasks:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(task.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.tasks });
      notify(t("task-cancel-notice", { id: task.id }));
      onDone?.();
    },
  });
  if (!allowed || task.status !== "running") return null;
  return (
    <Confirm
      trigger={
        <Button variant="destructive">
          <X /> {t("task-cancel-action")}
        </Button>
      }
      title={t("task-cancel-title")}
      confirm={t("task-cancel")}
      onConfirm={() => cancel.mutateAsync()}
    >
      {t("task-cancel-description")}
    </Confirm>
  );
}
