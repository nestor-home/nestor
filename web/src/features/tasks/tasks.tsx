/**
 * A task, opened: in a side sheet from where it is listed (its thread, and the composer at the sheet's foot), and on
 * its own page with its whole story (the thread, what it is about, then its trace in the journal).
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, Workflow } from "lucide-react";
import { isMissing, type Task, type TaskThread, taskQuery } from "@/api";
import { Ago } from "@/components/ago";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { Avatar } from "@/components/marks";
import { OriginLink } from "@/components/origin-link";
import { SheetPanel } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, Panel, Section, WithAside } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { KindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { TaskComposer, WriteToTask } from "./composer";
import { TaskActions, TaskStateMark } from "./parts";
import { Notes, Thread } from "./thread";

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
            <TaskStateMark state={task.state} />
            <KindName kind={task.executor} />
            <span>
              <Ago iso={task.last_activity} />
            </span>
          </>
        }
        actions={
          <span className="flex flex-wrap gap-2">
            <WriteToTask task={task} />
            <TaskActions task={task} />
          </span>
        }
      />
      <div className="grid gap-10">
        <WithAside>
          <Section title={t("task-thread")} count={task.turns}>
            <Panel>
              <Thread task={task} />
            </Panel>
          </Section>
          <div className="grid content-start gap-6">
            <About task={task} />
            <Notes notes={task.notes} />
          </div>
        </WithAside>
        <Section title={t("task-story")}>
          <SubjectStory filters={{ task: task.id }} empty={t("task-story-empty")} />
        </Section>
      </div>
    </>
  );
}

/** Who it is for and where it was asked, who does it, since when. */
function About({ task }: { task: Task }) {
  const t = useT();
  return (
    <Panel as="aside" aria-label={t("task-about")}>
      <Facts narrow className="text-body">
        <Fact term={t("task-about-state")}>
          <TaskStateMark state={task.state} />
        </Fact>
        {task.owner ? (
          <Fact term={t("task-asked-by")} className="flex items-center gap-2">
            <Avatar name={task.owner.name} size="sm" />
            {task.owner.name}
          </Fact>
        ) : null}
        <Fact term={t("task-asked-in")}>
          <OriginLink origin={task.origin} />
        </Fact>
        <Fact term={t("task-done-by")}>
          <KindName kind={task.executor} />
        </Fact>
        <Fact term={t("task-started")}>{moment(task.created_at)}</Fact>
      </Facts>
    </Panel>
  );
}

/**
 * A task in a side sheet: its thread to read, the composer at its foot to answer or reorient it, and the way to its
 * page and to what one can do with it. `listed` shows what the list knows while the thread loads.
 */
export function TaskSheet({ listed, onArchived }: { listed: Task; onArchived: () => void }) {
  const t = useT();
  const found = useQuery(taskQuery(listed.id));
  const task: Task = found.data ?? listed;
  return (
    <SheetPanel
      icon={Workflow}
      tone="task"
      kind={t("act-kind-task")}
      title={task.title}
      description={
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <TaskStateMark state={task.state} />
          <KindName kind={task.executor} />
          {task.owner ? <span>{t("task-for", { name: task.owner.name })}</span> : null}
        </span>
      }
      actions={
        <div className="grid w-full gap-3">
          <TaskComposer task={task} />
          <div className="flex flex-wrap gap-2">
            <Link to="/tasks/$taskId" params={{ taskId: task.id }} className={buttonVariants({ variant: "outline" })}>
              {t("act-open-page")} <ArrowUpRight />
            </Link>
            <TaskActions task={task} onArchived={onArchived} />
          </div>
        </div>
      }
    >
      <SheetThread found={found.data} pending={found.isPending} error={found.error} />
    </SheetPanel>
  );
}

function SheetThread({ found, pending, error }: { found?: TaskThread; pending: boolean; error: unknown }) {
  if (found)
    return (
      <>
        <Thread task={found} follow />
        <Notes notes={found.notes} />
      </>
    );
  if (pending) return <Loading lines={4} />;
  return <Failure error={error} />;
}
