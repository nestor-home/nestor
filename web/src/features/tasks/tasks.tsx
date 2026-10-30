import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, MessageSquareText, Volume2 } from "lucide-react";
import { api, isMissing, keys, type Task, type TaskStatus, taskQuery, tasksQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { Button } from "@/components/ui/button";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { BrandMark, brandOf, KindMark } from "@/lib/brands";
import { taskStatusLabel } from "@/lib/labels";
import { usePeopleNames } from "@/lib/people";
import { useCan } from "@/lib/session";
import { duration } from "@/lib/time";

const TONE: Record<TaskStatus, StatusTone> = { running: "accent", completed: "ok", failed: "error", cancelled: "idle" };

export function TaskStatusMark({ status }: { status: TaskStatus }) {
  return <Status tone={TONE[status]}>{taskStatusLabel(status)}</Status>;
}

function Executor({ name }: { name: string }) {
  const brand = brandOf(name);
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ink-muted">
      {brand ? <BrandMark brand={brand} className="size-3.5" label={false} /> : null}
      {name}
    </span>
  );
}

export function TasksList() {
  const t = useT();
  const tasks = useQuery(tasksQuery);
  if (tasks.isPending) return <Loading lines={3} />;
  if (tasks.isError) return <Failure error={tasks.error} retry={() => void tasks.refetch()} />;
  return (
    <>
      <Section title={t("task-running")} count={tasks.data.running.length}>
        {tasks.data.running.length === 0 ? (
          <Empty hint={t("task-running-empty-hint")}>{t("task-running-empty")}</Empty>
        ) : (
          <TaskRows tasks={tasks.data.running} />
        )}
      </Section>
      <Section title={t("task-done")} count={tasks.data.recent.length}>
        {tasks.data.recent.length === 0 ? (
          <Empty>{t("task-done-empty")}</Empty>
        ) : (
          <TaskRows tasks={tasks.data.recent} />
        )}
      </Section>
    </>
  );
}

function TaskRows({ tasks }: { tasks: Task[] }) {
  const t = useT();
  const name = usePeopleNames();
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {tasks.map((task) => (
        <li key={task.id}>
          <Link
            to="/tasks/$taskId"
            params={{ taskId: task.id }}
            className="group grid gap-x-6 gap-y-1 px-5 py-3.5 hover:bg-paper-sunken/60 sm:grid-cols-[minmax(0,1fr)_8rem_1rem] sm:items-center"
          >
            <span className="min-w-0">
              <span className="block text-ink">{task.objective}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-x-3 font-mono text-[0.7rem] text-ink-muted">
                <Executor name={task.executor} />
                {task.requested_by ? <span>{t("task-for", { name: name(task.requested_by) })}</span> : null}
                <span>
                  {task.status === "running" ? (
                    <>
                      {t("task-since")} <Ago iso={task.started_at} />
                    </>
                  ) : task.ended_at ? (
                    <Ago iso={task.ended_at} />
                  ) : null}
                </span>
                {task.status === "running" && task.steps.length ? (
                  <span className="truncate text-ink">{task.steps.at(-1)}</span>
                ) : null}
              </span>
            </span>
            <TaskStatusMark status={task.status} />
            <ArrowRight className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function TaskDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(taskQuery(id));
  const name = usePeopleNames();
  const canCancel = useCan("tasks:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.tasks });
      notify(t("task-cancel-notice", { id }));
    },
  });
  const trail: Crumb[] = [{ label: t("task-title"), link: { to: "/tasks" } }, { label: id }];
  if (found.isPending) return <Loading lines={4} />;
  const task = found.data;
  if (!task) {
    return (
      <>
        <Crumbs trail={trail} />
        {isMissing(found.error) ? <Empty>{t("task-unknown")}</Empty> : <Failure error={found.error} />}
      </>
    );
  }
  const took = task.ended_at ? (new Date(task.ended_at).getTime() - new Date(task.started_at).getTime()) / 1000 : null;
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={task.objective}
        meta={
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-muted">
            <TaskStatusMark status={task.status} />
            <Executor name={task.executor} />
            {task.requested_by ? <span>{t("task-requested-by", { name: name(task.requested_by) })}</span> : null}
            <span>
              <Ago iso={task.started_at} />
            </span>
            {took ? <span>{t("task-took", { duration: duration(took) })}</span> : null}
          </p>
        }
        actions={
          task.status === "running" && canCancel ? (
            <Confirm
              trigger={<Button variant="destructive">{t("task-cancel-action")}</Button>}
              title={t("task-cancel-title")}
              confirm={t("task-cancel")}
              onConfirm={() => cancel.mutateAsync()}
            >
              {t("task-cancel-description")}
            </Confirm>
          ) : null
        }
      />
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] [&>*]:min-w-0">
        <Section title={t("task-story")}>
          <SubjectStory filters={{ task: task.id }} empty={t("task-story-empty")} />
        </Section>
        <aside className="grid content-start gap-6">
          {task.result || task.error ? (
            <div>
              <p className="label-mono mb-1.5">{task.error ? t("task-error") : t("task-result")}</p>
              <p className={task.error ? "text-sm text-brick" : "font-serif text-[1.05rem] leading-relaxed"}>
                {task.error ?? task.result}
              </p>
            </div>
          ) : null}
          {task.origin ? (
            <div>
              <p className="label-mono mb-1.5">{t("task-asked-in")}</p>
              {task.origin.session ? (
                <Link
                  to="/journal"
                  search={{ session: task.origin.session }}
                  className="inline-flex items-center gap-2 text-sm text-ink hover:text-ember"
                >
                  <MessageSquareText className="size-4" aria-hidden="true" />
                  {t("task-a-conversation")}
                  {task.origin.channel ? (
                    <span className="inline-flex items-center gap-1 font-mono text-xs text-ink-muted">
                      <KindMark kind={task.origin.channel} className="size-3" label={false} />
                      {task.origin.channel}
                    </span>
                  ) : null}
                </Link>
              ) : (
                <p className="text-sm text-ink-muted">{t("task-conversation-older")}</p>
              )}
            </div>
          ) : null}
          <div>
            <p className="label-mono mb-1.5">{t("task-delivery")}</p>
            {task.delivered ? (
              <p className="flex items-start gap-2 text-sm">
                <Volume2 className="mt-0.5 size-4 shrink-0 text-ember" aria-hidden="true" />
                <span>
                  {t("task-delivered", {
                    spoken: task.delivered.channel === "voice" ? "yes" : "no",
                    channel: task.delivered.channel,
                    room: task.delivered.room ?? "none",
                  })}{" "}
                  <Ago iso={task.delivered.at} className="font-[inherit]" />
                </span>
              </p>
            ) : (
              <p className="text-sm text-ink-muted">
                {task.status === "running" ? t("task-delivery-pending") : t("task-delivery-none")}
              </p>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}
