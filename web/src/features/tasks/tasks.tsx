/**
 * A task's whole run on its page: what was asked and where it stands, its outcome and the files it made,
 * who asked and how the answer reached them, its steps as they came, then its trace in the journal.
 */
import { useQuery } from "@tanstack/react-query";
import { Paperclip, TriangleAlert, Volume2, Workflow } from "lucide-react";
import { isMissing, type Task, taskQuery } from "@/api";
import { API_BASE } from "@/api/client";
import { Ago } from "@/components/ago";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { Avatar, IconTile } from "@/components/marks";
import { OriginLink } from "@/components/origin-link";
import { Fact, Facts, PageHeader, Panel, Section, WithAside } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Files } from "@/features/journal/attachments";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { KindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { duration } from "@/lib/time";
import { CancelTask, Steps, TaskStatusMark } from "./parts";

export function TaskDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(taskQuery(id));
  const trail: Crumb[] = [
    { label: t("space-activity"), link: { to: "/activity" } },
    { label: found.data?.title ?? id },
  ];
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
        title={task.title}
        meta={
          <>
            <TaskStatusMark status={task.status} />
            <KindName kind={task.executor} />
            <span>
              <Ago iso={task.started_at} />
            </span>
          </>
        }
        actions={<CancelTask task={task} />}
      >
        {task.objective}
      </PageHeader>
      <div className="grid gap-10">
        <WithAside>
          <Outcome task={task} />
          <About task={task} />
        </WithAside>
        {task.steps.length ? (
          <Section title={t("task-steps")} count={task.steps.length}>
            <Steps task={task} className="surface px-5 pt-5 pb-1.5" />
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
      <p className="mb-2.5 flex items-center gap-1.5 text-body font-medium text-ink-muted">
        <Paperclip className="size-3.5" aria-hidden="true" />
        {t("task-files", { count: task.files.length })}
      </p>
      <Files files={task.files} url={(index) => `${API_BASE}/tasks/${task.id}/files/${index}`} />
    </div>
  ) : null;

  if (task.status === "running") {
    return (
      <Section title={t("task-now")}>
        <Panel>
          <div className="flex items-start gap-4">
            <IconTile icon={Workflow} tone="task" />
            <p className="min-w-0 flex-1 self-center title-sub text-ink">{task.steps.at(-1) ?? t("task-starting")}</p>
          </div>
          <span className="thread mt-4 block" aria-hidden="true" />
          <p className="mt-3 text-body text-ink-muted">{t("task-delivery-pending")}</p>
          {files}
        </Panel>
      </Section>
    );
  }
  if (task.error) {
    return (
      <Section title={t("task-error")}>
        <Panel>
          <div className="flex items-start gap-4">
            <IconTile icon={TriangleAlert} tone="brick" />
            <p className="min-w-0 flex-1 self-center whitespace-pre-line text-brick">{task.error}</p>
          </div>
          {files}
        </Panel>
      </Section>
    );
  }
  if (task.result || files) {
    return (
      <Section title={t("task-result")}>
        <Panel marked>
          {task.result ? (
            <p className="min-w-0 max-w-2xl whitespace-pre-line font-serif text-heading leading-relaxed text-ink">
              {task.result}
            </p>
          ) : null}
          {files}
        </Panel>
      </Section>
    );
  }
  return (
    <Section title={t("task-result")}>
      <Empty>{t(task.status === "cancelled" ? "task-stopped-early" : "task-no-result")}</Empty>
    </Section>
  );
}

/** The facts around the run: who asked and where, who did it, how long it took, how the answer arrived. */
function About({ task }: { task: Task }) {
  const t = useT();
  const took = task.ended_at ? (new Date(task.ended_at).getTime() - new Date(task.started_at).getTime()) / 1000 : null;
  return (
    <Panel as="aside" aria-label={t("task-about")} className="self-start">
      <Facts narrow className="text-body">
        {task.requested_by ? (
          <Fact term={t("task-asked-by")} className="flex items-center gap-2">
            <Avatar name={task.requested_by.name} size="sm" />
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
          <KindName kind={task.executor} />
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
    </Panel>
  );
}
