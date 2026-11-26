/**
 * "Ongoing": everything the agent does for the household on its own, by where it stands: what waits
 * for an answer, what runs, the alerts it keeps (with why each rang), what just ended. Each opens in a drawer.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { Archive, ArrowUpRight, BellRing, Check, CircleHelp, Plus, Send, ShieldQuestion, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  type Alert,
  alertsQuery,
  api,
  archivedTasksQuery,
  type Confirmation,
  confirmationsQuery,
  keys,
  messageOf,
  messagesQuery,
  type PassedMessage,
  type Task,
  tasksQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { CardHead } from "@/components/card";
import { Chips } from "@/components/chips";
import { Confirm } from "@/components/confirm";
import { Avatar, IconTile, type TileTone } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import { AlertFrequency, AlertKind, AlertMark, CancelAlert, RangBecause, rings } from "@/features/alerts/parts";
import { TaskCardBody, TaskLine, TaskStateMark } from "@/features/tasks/parts";
import { TaskSheet } from "@/features/tasks/tasks";
import { useT } from "@/i18n";
import { KindName } from "@/lib/brands";
import { agendaDay, hourMinute, moment } from "@/lib/dates";
import { frequencyLabel, turnStatusLabel } from "@/lib/labels";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";

type Lane = "all" | "you" | "running" | "alerts";
/** What the drawer shows, looked up in the lists at each render so that it follows them. */
type Opened = { kind: "task" | "alert"; id: string };

export function ActivityView() {
  const t = useT();
  const me = useMe();
  // a lane shows only to whoever may read what it holds
  const can: Record<Lane, boolean> = {
    all: true,
    you: useCan("messages:read"),
    running: useCan("tasks:read"),
    alerts: useCan("alerts:read"),
  };
  const confirmations = useQuery({ ...confirmationsQuery, enabled: can.you });
  const messages = useQuery({ ...messagesQuery, enabled: can.you });
  const tasks = useQuery({ ...tasksQuery, enabled: can.running });
  const alerts = useQuery({ ...alertsQuery, enabled: can.alerts });
  const canConfigure = useCan("config:manage");
  const [lane, setLane] = useState<Lane>("all");
  const [opened, setOpened] = useState<Opened | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const archived = useQuery({ ...archivedTasksQuery, enabled: can.running && showArchived });

  const asks = confirmations.data ?? [];
  const questions = messages.data?.questions ?? [];
  const pending = messages.data?.pending ?? [];
  const listed = tasks.data?.tasks ?? [];
  const asking = listed.filter((x) => x.state === "waiting");
  const running = listed.filter((x) => x.state === "working");
  const ready = listed.filter((x) => x.state === "ready");
  const put = archived.data?.tasks ?? [];
  const kept = alerts.data?.alerts ?? []; // soonest due first, then those that wait for items
  const noSource = alerts.data?.kinds.length === 0;
  const others = lane === "running" ? 0 : asks.length + questions.length + pending.length;
  const waiting = asks.length + questions.length + pending.length + asking.length;
  const lanes = (
    [
      { id: "all", label: t("act-all"), count: 0 },
      { id: "you", label: t("act-you"), count: waiting },
      { id: "running", label: t("act-running"), count: asking.length + running.length },
      { id: "alerts", label: t("act-alerts"), count: kept.length },
    ] satisfies { id: Lane; label: string; count: number }[]
  ).filter((l) => can[l.id]);
  const shows = (id: Lane) => can[id] && (lane === "all" || lane === id);
  const failed = confirmations.isError ? confirmations : messages.isError ? messages : null;
  const openTask = opened?.kind === "task" ? [...listed, ...put].find((x) => x.id === opened.id) : undefined;
  const openOne = (task: Task) => setOpened({ kind: "task", id: task.id });
  const openAlert = opened?.kind === "alert" ? kept.find((x) => x.id === opened.id) : undefined;
  const close = () => setOpened(null);

  return (
    <div className="grid gap-10">
      <div>
        <PageHeader title={t("act-title")}>{t("act-lede", { assistant: me.assistant })}</PageHeader>
        <Chips label={t("act-title")} items={lanes} value={lane} onChange={setLane} />
      </div>

      {(shows("you") && (waiting || failed || lane === "you")) || (lane === "running" && asking.length) ? (
        <Section title={t("act-you-title")} count={others + asking.length}>
          {failed && lane !== "running" ? (
            <Failure error={failed.error} retry={() => void failed.refetch()} />
          ) : others + asking.length ? (
            <ul className="grid gap-3 lg:grid-cols-2">
              {asking.map((task) => (
                <TaskItem key={task.id} task={task} onOpen={openOne} />
              ))}
              {(lane === "running" ? [] : asks).map((c) => (
                <ConfirmationCard key={c.id} confirmation={c} />
              ))}
              {(lane === "running" ? [] : questions).map((m) => (
                <MessageCard
                  key={m.id}
                  message={m}
                  icon={CircleHelp}
                  tone="amber"
                  state={<Status tone="pending">{t("act-awaits-reply")}</Status>}
                />
              ))}
              {(lane === "running" ? [] : pending).map((m) => (
                <MessageCard
                  key={m.id}
                  message={m}
                  icon={Send}
                  tone="ink"
                  state={<Status tone="idle">{t("act-on-its-way")}</Status>}
                />
              ))}
            </ul>
          ) : (
            <Empty>{t("act-you-empty")}</Empty>
          )}
        </Section>
      ) : null}

      {shows("running") ? (
        <Section title={t("act-running-title")} count={running.length} aside={<Ask />}>
          {tasks.isError ? (
            <Failure error={tasks.error} retry={() => void tasks.refetch()} />
          ) : tasks.isPending ? (
            <Loading lines={2} />
          ) : running.length ? (
            <ul className="grid gap-3 lg:grid-cols-2">
              {running.map((task) => (
                <TaskItem key={task.id} task={task} onOpen={openOne} />
              ))}
            </ul>
          ) : (
            <Empty>{t("task-running-empty-hint")}</Empty>
          )}
        </Section>
      ) : null}

      {shows("alerts") ? (
        <Section title={t("act-alerts-title")} count={kept.length} aside={<Ask />}>
          {alerts.isError ? (
            <Failure error={alerts.error} retry={() => void alerts.refetch()} />
          ) : alerts.isPending ? (
            <Loading lines={2} />
          ) : kept.length ? (
            <RowList ordered>
              {kept.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className="grid w-full grid-cols-[minmax(4.5rem,auto)_1fr_auto] items-center gap-x-5 px-4 py-3.5 text-left hover:bg-paper-sunken/60"
                    onClick={() => setOpened({ kind: "alert", id: a.id })}
                  >
                    {a.next_due ? <When iso={a.next_due} /> : <AlertMark alert={a} size="sm" />}
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{a.title}</span>
                      <span className="line-clamp-1 block text-body text-ink-muted">
                        {a.condition ?? a.instruction}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-meta text-ink-muted">
                        <span className="min-w-0">{rings(a)}</span>
                        <span className="min-w-0">{frequencyLabel(a.frequency)}</span>
                        {a.rings[0] ? (
                          <span className="flex min-w-0 items-baseline gap-1.5 text-ink">
                            <BellRing className="size-3.5 shrink-0 translate-y-0.5 text-ember" aria-hidden="true" />
                            <span className="min-w-0">
                              <RangBecause ring={a.rings[0]} />
                            </span>
                          </span>
                        ) : null}
                      </span>
                    </span>
                    {a.owner ? <Avatar name={a.owner.name} /> : null}
                  </button>
                </li>
              ))}
            </RowList>
          ) : (
            <Empty
              hint={noSource ? t("act-no-source-hint", { assistant: me.assistant }) : undefined}
              action={
                noSource ? (
                  <span className="flex flex-wrap gap-2">
                    <Link to="/connections/catalogue" className={buttonVariants({ variant: "outline", size: "sm" })}>
                      {t("act-connect-account")}
                    </Link>
                    {canConfigure ? (
                      <Link
                        to="/config/$section"
                        params={{ section: "inbound" }}
                        className={buttonVariants({ variant: "outline", size: "sm" })}
                      >
                        {t("act-add-source")}
                      </Link>
                    ) : null}
                  </span>
                ) : undefined
              }
            >
              {t("alert-empty-hint", { assistant: me.assistant })}
            </Empty>
          )}
        </Section>
      ) : null}

      {shows("running") && (ready.length || lane === "running" || showArchived) ? (
        <Section
          title={t("act-ready-title")}
          count={ready.length}
          aside={
            <Button variant="ghost" size="sm" aria-pressed={showArchived} onClick={() => setShowArchived((x) => !x)}>
              <Archive /> {t(showArchived ? "act-archived-hide" : "act-archived-show")}
            </Button>
          }
        >
          {ready.length ? (
            <TaskRows tasks={lane === "running" ? ready : ready.slice(0, 6)} onOpen={openOne} />
          ) : (
            <Empty>{t("act-ready-empty")}</Empty>
          )}
          {showArchived ? (
            <div className="mt-6 grid gap-3">
              <h3 className="title-sub text-ink">{t("act-archived-title")}</h3>
              {archived.isError ? (
                <Failure error={archived.error} retry={() => void archived.refetch()} />
              ) : archived.isPending ? (
                <Loading lines={2} />
              ) : put.length ? (
                <TaskRows tasks={put} onOpen={openOne} />
              ) : (
                <Empty>{t("act-archived-empty")}</Empty>
              )}
            </div>
          ) : null}
        </Section>
      ) : null}

      <SideSheet open={Boolean(openTask ?? openAlert)} onOpenChange={(open) => !open && close()}>
        {openTask ? <TaskSheet listed={openTask} onArchived={close} /> : null}
        {openAlert ? <AlertPanel alert={openAlert} onDone={close} /> : null}
      </SideSheet>
    </div>
  );
}

/** A task as a card that opens it: its question when it waits, its latest step when it works. */
function TaskItem({ task, onOpen }: { task: Task; onOpen: (task: Task) => void }) {
  return (
    <li>
      <button type="button" className="surface block h-full w-full p-4 text-left" onClick={() => onOpen(task)}>
        <TaskCardBody task={task} />
      </button>
    </li>
  );
}

/** Tasks that wait for nothing, as rows: their title, who does them, when they last moved, their state. */
function TaskRows({ tasks, onOpen }: { tasks: Task[]; onOpen: (task: Task) => void }) {
  return (
    <RowList>
      {tasks.map((task) => (
        <li key={task.id}>
          <button
            type="button"
            className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 px-4 py-3 text-left hover:bg-paper-sunken/60"
            onClick={() => onOpen(task)}
          >
            <span className="min-w-0">
              <span className="line-clamp-1 block text-ink">{task.title}</span>
              <TaskLine task={task} className="text-meta text-ink-muted">
                <LastTurn task={task} />
              </TaskLine>
            </span>
            {task.owner ? <Avatar name={task.owner.name} /> : <TaskStateMark state={task.state} />}
          </button>
        </li>
      ))}
    </RowList>
  );
}

/** How the last turn of a task that waits for nothing ended, when it did not come back: failed, or stopped. */
function LastTurn({ task }: { task: Task }) {
  if (task.last_status === "failed") return <Status tone="error">{turnStatusLabel(task.last_status)}</Status>;
  if (task.last_status === "stopped") return <Status tone="idle">{turnStatusLabel(task.last_status)}</Status>;
  return null;
}

/** Alerts and tasks are made by asking: the way to the agent, from where one looks at them. */
function Ask() {
  const t = useT();
  const me = useMe();
  if (!useCan("chat:write")) return null;
  return (
    <Link to="/chat" className={buttonVariants({ variant: "outline", size: "sm" })}>
      <Plus /> {t("act-ask", { assistant: me.assistant })}
    </Link>
  );
}

/** The day over the hour: the left edge of a planned row, read like an agenda. */
function When({ iso }: { iso: string | null }) {
  if (!iso) return <span className="text-ink-faint">·</span>;
  return (
    <time dateTime={iso} className="grid">
      <span className="text-meta text-ink-muted first-letter:uppercase">{agendaDay(iso)}</span>
      <span className="title-card text-ink tabular">{hourMinute(iso)}</span>
    </time>
  );
}

/** A sensitive action waiting for its person: approve it here, or refuse. */
function ConfirmationCard({ confirmation: c }: { confirmation: Confirmation }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const answer = useMutation({
    mutationFn: (approved: boolean) => api.answerConfirmation(c.id, approved),
    onSuccess: (answered) => {
      void queryClient.invalidateQueries({ queryKey: keys.confirmations });
      notify(answered.approved ? t("confirmation-done-notice") : t("confirmation-refused-notice"));
    },
  });
  const what = Object.entries(c.arguments)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
    .join(" · ");
  return (
    <li className="surface p-4">
      <CardHead
        mark={<IconTile icon={ShieldQuestion} tone="amber" />}
        title={<span className="font-mono">{c.tool}</span>}
        line={what || null}
        aside={<Status tone="attention">{t("act-awaits-approval")}</Status>}
      >
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-muted">
          <span>{t("confirmation-for", { name: personName(c.person) })}</span>
          <KindName kind={c.origin.channel} />
          <span>{t("confirmation-expires", { at: hourMinute(c.expires_at) })}</span>
        </span>
        {c.yours ? (
          <span className="flex flex-wrap gap-2">
            <Confirm
              trigger={
                <Button size="sm" disabled={answer.isPending}>
                  <Check /> {t("confirmation-approve")}
                </Button>
              }
              title={t("confirmation-approve-title")}
              confirm={t("confirmation-approve")}
              onConfirm={() => answer.mutateAsync(true)}
              tone="accent"
            >
              {t("confirmation-approve-description", { tool: c.tool })}
            </Confirm>
            <Button
              variant="outline"
              size="sm"
              disabled={answer.isPending}
              onClick={() => answer.mutate(false, { onError: (error) => notify(messageOf(error)) })}
            >
              <X /> {t("confirmation-refuse")}
            </Button>
          </span>
        ) : (
          <span className="text-meta text-ink-muted">{t("confirmation-not-yours")}</span>
        )}
      </CardHead>
    </li>
  );
}

function MessageCard({
  message: m,
  icon,
  tone,
  state,
}: {
  message: PassedMessage;
  icon: LucideIcon;
  tone: TileTone;
  state: ReactNode;
}) {
  const t = useT();
  return (
    <li className="surface p-4">
      <CardHead mark={<IconTile icon={icon} tone={tone} />} title={t("message-quoted", { text: m.text })} aside={state}>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-muted">
          <span>
            {m.requested_by
              ? t("message-from-to", { from: m.requested_by.name, to: m.to.name })
              : t("message-to", { to: m.to.name })}
          </span>
          {m.channel ? <KindName kind={m.channel} /> : null}
          <Ago iso={m.at} />
        </span>
      </CardHead>
    </li>
  );
}

// -- the drawers ----------------------------------------------------------------------------------

function AlertPanel({ alert: a, onDone }: { alert: Alert; onDone: () => void }) {
  const t = useT();
  return (
    <SheetPanel
      icon={BellRing}
      tone="alert"
      kind={t("act-kind-alert")}
      title={a.title}
      description={a.instruction}
      actions={
        <>
          <Link to="/alerts/$alertId" params={{ alertId: a.id }} className={buttonVariants({ variant: "outline" })}>
            {t("alert-found")} <ArrowUpRight />
          </Link>
          <CancelAlert alert={a} onDone={onDone} />
        </>
      }
    >
      <Facts narrow className="text-body">
        <Fact term={t("alert-trigger")}>
          {a.trigger === "events" ? (
            <span className="flex flex-wrap gap-x-3">
              {a.kinds.map((k) => (
                <AlertKind key={k} kind={k} />
              ))}
            </span>
          ) : (
            rings(a)
          )}
        </Fact>
        {a.next_due ? <Fact term={t("act-next")}>{moment(a.next_due)}</Fact> : null}
        {a.condition ? <Fact term={t("alert-condition")}>{a.condition}</Fact> : null}
        <Fact term={t("alert-frequency-term")}>
          <AlertFrequency alert={a} />
        </Fact>
        <Fact term={t("act-for")}>{personName(a.owner)}</Fact>
        <Fact term={t("alert-so-far")}>
          {a.rings[0] ? (
            <>
              {t("alert-rang-count", { count: a.rang })}
              <span className="block text-meta text-ink-muted">
                <RangBecause ring={a.rings[0]} />
              </span>
            </>
          ) : (
            t("alert-never-rang")
          )}
        </Fact>
        {a.until ? <Fact term={t("act-until")}>{moment(a.until)}</Fact> : null}
        {a.origin ? (
          <Fact term={t("alert-asked-in")}>
            <OriginLink origin={a.origin} />
          </Fact>
        ) : null}
      </Facts>
    </SheetPanel>
  );
}
