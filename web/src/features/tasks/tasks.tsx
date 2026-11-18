/**
 * A task's whole run on its page: what was asked and where it stands, its outcome and the files it made,
 * who asked and how the answer reached them, its steps as they came, then its trace in the journal.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleSlash, Paperclip, TriangleAlert, Volume2, Workflow, X } from "lucide-react";
import { api, isMissing, keys, type Task, type TaskStatus, taskQuery } from "@/api";
import { API_BASE } from "@/api/client";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { IconTile, Pebble } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { Fact, Facts, PageHeader, Section, WithAside } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Files } from "@/features/journal/attachments";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { BrandMark, brandName, brandOf } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { taskStatusLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";

const TONE: Record<TaskStatus, StatusTone> = { running: "accent", completed: "ok", failed: "error", cancelled: "idle" };

export function TaskStatusMark({ status }: { status: TaskStatus }) {
  return <Status tone={TONE[status]}>{taskStatusLabel(status)}</Status>;
}

/** Who does the work: the executor's mark and the name people know it by. */
function Executor({ name }: { name: string }) {
  const brand = brandOf(name);
  return (
    <span className="inline-flex items-center gap-1.5">
      {brand ? <BrandMark brand={brand} className="size-3.5" label={false} /> : null}
      {brand ? brandName(brand) : name}
    </span>
  );
}

export function TaskDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(taskQuery(id));
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
  const trail: Crumb[] = [{ label: t("space-activity"), link: { to: "/activity" } }, { label: id }];
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
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={task.objective}
        meta={
          <>
            <TaskStatusMark status={task.status} />
            <Executor name={task.executor} />
            <span>
              <Ago iso={task.started_at} />
            </span>
          </>
        }
        actions={
          task.status === "running" && canCancel ? (
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
          ) : null
        }
      />
      <div className="grid gap-10">
        <WithAside>
          <Outcome task={task} />
          <About task={task} />
        </WithAside>
        {task.steps.length ? (
          <Section title={t("task-steps")} count={task.steps.length}>
            <Steps task={task} />
          </Section>
        ) : null}
        <Section title={t("task-story")}>
          <SubjectStory filters={{ task: task.id }} empty={t("task-story-empty")} />
        </Section>
      </div>
    </>
  );
}

/** Where the task stands, as the first thing read: what it is doing, what it gave back, or why it gave nothing. */
function Outcome({ task }: { task: Task }) {
  const t = useT();
  const files = task.files.length ? (
    <div className={task.result || task.error ? "mt-5 border-t border-rule pt-4" : undefined}>
      <p className="mb-2.5 flex items-center gap-1.5 text-[0.9rem] font-medium text-ink-muted">
        <Paperclip className="size-3.5" aria-hidden="true" />
        {t("task-files", { count: task.files.length })}
      </p>
      <Files files={task.files} url={(index) => `${API_BASE}/tasks/${task.id}/files/${index}`} />
    </div>
  ) : null;

  if (task.status === "running") {
    return (
      <Section title={t("task-now")}>
        <div className="surface p-5">
          <div className="flex items-start gap-4">
            <IconTile icon={Workflow} tone="task" />
            <p className="min-w-0 flex-1 self-center font-serif text-[1.2rem] leading-snug text-ink">
              {task.steps.at(-1) ?? t("task-starting")}
            </p>
          </div>
          <span className="thread mt-4 block" aria-hidden="true" />
          <p className="mt-3 text-[0.92rem] text-ink-muted">{t("task-delivery-pending")}</p>
          {files}
        </div>
      </Section>
    );
  }
  if (task.error) {
    return (
      <Section title={t("task-error")}>
        <div className="surface p-5">
          <div className="flex items-start gap-4">
            <IconTile icon={TriangleAlert} tone="brick" />
            <p className="min-w-0 flex-1 self-center whitespace-pre-line text-brick [overflow-wrap:anywhere]">
              {task.error}
            </p>
          </div>
          {files}
        </div>
      </Section>
    );
  }
  if (task.result || files) {
    return (
      <Section title={t("task-result")}>
        <div className="surface corner-marks relative p-5">
          {task.result ? (
            <p className="max-w-2xl whitespace-pre-line font-serif text-[1.15rem] leading-relaxed text-ink [overflow-wrap:anywhere]">
              {task.result}
            </p>
          ) : null}
          {files}
        </div>
      </Section>
    );
  }
  return (
    <Section title={t("task-result")}>
      <div className="surface-quiet flex items-center gap-4 px-4 py-5">
        <IconTile icon={CircleSlash} />
        <p className="text-[0.98rem] text-ink-muted">
          {t(task.status === "cancelled" ? "task-stopped-early" : "task-no-result")}
        </p>
      </div>
    </Section>
  );
}

/** The facts around the run: who asked and where, who did it, how long it took, how the answer arrived. */
function About({ task }: { task: Task }) {
  const t = useT();
  const took = task.ended_at ? (new Date(task.ended_at).getTime() - new Date(task.started_at).getTime()) / 1000 : null;
  return (
    <aside aria-label={t("task-about")} className="surface self-start p-5">
      <Facts narrow className="text-[0.95rem]">
        {task.requested_by ? (
          <Fact term={t("task-asked-by")} className="flex items-center gap-2">
            <Pebble name={task.requested_by.name} className="size-6 text-[0.65rem]" />
            {task.requested_by.name}
          </Fact>
        ) : null}
        {task.origin ? (
          <Fact term={t("task-asked-in")}>
            {task.origin.session ? (
              <OriginLink origin={task.origin} />
            ) : (
              <span className="text-ink-muted">{t("task-conversation-older")}</span>
            )}
          </Fact>
        ) : null}
        <Fact term={t("task-done-by")}>
          <Executor name={task.executor} />
        </Fact>
        <Fact term={t("task-started")}>{moment(task.started_at)}</Fact>
        {took ? <Fact term={t("task-took")}>{duration(took)}</Fact> : null}
        {task.status === "running" ? null : (
          <Fact term={t("task-delivery")}>
            {task.delivered ? (
              <span className="flex items-start gap-2">
                <Volume2 className="mt-0.5 size-4 shrink-0 text-ember" aria-hidden="true" />
                <span>
                  {t("task-delivered", {
                    spoken: task.delivered.channel === "voice" ? "yes" : "no",
                    channel: task.delivered.channel,
                    room: task.delivered.room ?? "none",
                  })}{" "}
                  <Ago iso={task.delivered.at} />
                </span>
              </span>
            ) : (
              <span className="text-ink-muted">{t("task-delivery-none")}</span>
            )}
          </Fact>
        )}
      </Facts>
    </aside>
  );
}

/** What the executor reported as it went, oldest first; the last one glows while the task runs. */
function Steps({ task }: { task: Task }) {
  return (
    <ol className="surface px-5 pt-5 pb-1.5">
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
            <span
              className={cn("pb-3.5 text-[0.95rem] [overflow-wrap:anywhere]", last ? "text-ink" : "text-ink-muted")}
            >
              {step}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
