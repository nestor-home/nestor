/**
 * "Ongoing": everything the agent does for the household on its own, by where it stands: what waits
 * for an answer, what runs, what is planned, what it watches, what just ended. Each opens in a drawer.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  Archive,
  ArrowUpRight,
  Check,
  CircleHelp,
  Plus,
  Radar,
  Repeat,
  Send,
  ShieldQuestion,
  Trash2,
  X,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  api,
  archivedTasksQuery,
  type Confirmation,
  confirmationsQuery,
  keys,
  messageOf,
  messagesQuery,
  type PassedMessage,
  type Schedule,
  schedulesQuery,
  type Task,
  tasksQuery,
  type Watch,
  watchesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, TILE_CARD, TileCard } from "@/components/card";
import { Chips } from "@/components/chips";
import { Confirm } from "@/components/confirm";
import { Avatar, BrandTile, IconTile, OwnerMark, type TileTone } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import { TaskCardBody, TaskStateMark } from "@/features/tasks/parts";
import { TaskSheet } from "@/features/tasks/tasks";
import { CancelWatch, WatchKind, watchBrand } from "@/features/watches/parts";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { KindName } from "@/lib/brands";
import { agendaDay, hourMinute, moment } from "@/lib/dates";
import { turnStatusLabel, weekdayLabel } from "@/lib/labels";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";

type Lane = "all" | "you" | "running" | "planned" | "watching";
/** What the drawer shows, looked up in the lists at each render so that it follows them. */
type Opened = { kind: "task" | "watch" | "schedule"; id: string };

export function ActivityView() {
  const t = useT();
  const me = useMe();
  // a lane shows only to whoever may read what it holds
  const can: Record<Lane, boolean> = {
    all: true,
    you: useCan("messages:read"),
    running: useCan("tasks:read"),
    planned: useCan("schedules:read"),
    watching: useCan("watches:read"),
  };
  const confirmations = useQuery({ ...confirmationsQuery, enabled: can.you });
  const messages = useQuery({ ...messagesQuery, enabled: can.you });
  const tasks = useQuery({ ...tasksQuery, enabled: can.running });
  const schedules = useQuery({ ...schedulesQuery, enabled: can.planned });
  const watches = useQuery({ ...watchesQuery, enabled: can.watching });
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
  const planned = [...(schedules.data?.schedules ?? [])].sort((a, b) =>
    (a.next_due ?? "9").localeCompare(b.next_due ?? "9"),
  );
  const watching = watches.data?.watches ?? [];
  const others = lane === "running" ? 0 : asks.length + questions.length + pending.length;
  const waiting = asks.length + questions.length + pending.length + asking.length;
  const lanes = (
    [
      { id: "all", label: t("act-all"), count: 0 },
      { id: "you", label: t("act-you"), count: waiting },
      { id: "running", label: t("act-running"), count: asking.length + running.length },
      { id: "planned", label: t("act-planned"), count: planned.length },
      { id: "watching", label: t("act-watching"), count: watching.length },
    ] satisfies { id: Lane; label: string; count: number }[]
  ).filter((l) => can[l.id]);
  const shows = (id: Lane) => can[id] && (lane === "all" || lane === id);
  const failed = confirmations.isError ? confirmations : messages.isError ? messages : null;
  const openTask = opened?.kind === "task" ? [...listed, ...put].find((x) => x.id === opened.id) : undefined;
  const openOne = (task: Task) => setOpened({ kind: "task", id: task.id });
  const openWatch = opened?.kind === "watch" ? watching.find((x) => x.id === opened.id) : undefined;
  const openSchedule = opened?.kind === "schedule" ? planned.find((x) => x.id === opened.id) : undefined;
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

      {shows("planned") ? (
        <Section title={t("act-planned-title")} count={planned.length} aside={<Ask />}>
          {schedules.isError ? (
            <Failure error={schedules.error} retry={() => void schedules.refetch()} />
          ) : schedules.isPending ? (
            <Loading lines={2} />
          ) : planned.length ? (
            <RowList ordered>
              {planned.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className="grid w-full grid-cols-[minmax(4.5rem,auto)_1fr_auto] items-center gap-x-5 px-4 py-3.5 text-left hover:bg-paper-sunken/60"
                    onClick={() => setOpened({ kind: "schedule", id: s.id })}
                  >
                    <When iso={s.next_due} />
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{s.title}</span>
                      <span className="line-clamp-1 block text-body text-ink-muted">{s.instruction}</span>
                      {s.recurring ? (
                        <span className="mt-0.5 flex items-center gap-1.5 text-meta text-ink-muted">
                          <Repeat className="size-3.5" aria-hidden="true" />
                          {rhythm(s)}
                        </span>
                      ) : null}
                    </span>
                    {s.owner ? <Avatar name={s.owner.name} /> : null}
                  </button>
                </li>
              ))}
            </RowList>
          ) : (
            <Empty>{t("schedule-empty-hint", { assistant: me.assistant })}</Empty>
          )}
        </Section>
      ) : null}

      {shows("watching") ? (
        <Section title={t("act-watching-title")} count={watching.length} aside={<Ask />}>
          {watches.isError ? (
            <Failure error={watches.error} retry={() => void watches.refetch()} />
          ) : watches.isPending ? (
            <Loading lines={2} />
          ) : watching.length ? (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {watching.map((w) => (
                <li key={w.id}>
                  <button type="button" className={TILE_CARD} onClick={() => setOpened({ kind: "watch", id: w.id })}>
                    <TileCard
                      marks={<BrandTile brand={watchBrand(w.kinds[0])} />}
                      aside={<OwnerMark owner={w.owner} />}
                      title={w.title}
                      line={<span className="line-clamp-2">{w.what}</span>}
                      foot={
                        <>
                          <span className="flex flex-wrap gap-x-3">
                            {w.kinds.map((k) => (
                              <WatchKind key={k} kind={k} />
                            ))}
                          </span>
                          <span className={w.triggered ? "font-medium text-ember" : ""}>
                            {w.triggered
                              ? t("watch-triggered-count", { count: w.triggered })
                              : t("watch-never-triggered")}
                          </span>
                        </>
                      }
                    />
                  </button>
                </li>
              ))}
            </ul>
          ) : watches.data && watches.data.kinds.length === 0 ? (
            <Empty
              hint={t("act-no-source-hint", { assistant: me.assistant })}
              action={
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
              }
            >
              {t("act-no-source")}
            </Empty>
          ) : (
            <Empty>{t("watch-active-empty-hint")}</Empty>
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

      <SideSheet open={Boolean(openTask ?? openWatch ?? openSchedule)} onOpenChange={(open) => !open && close()}>
        {openTask ? <TaskSheet listed={openTask} onArchived={close} /> : null}
        {openWatch ? <WatchPanel watch={openWatch} onDone={close} /> : null}
        {openSchedule ? <SchedulePanel schedule={openSchedule} onDone={close} /> : null}
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
  const t = useT();
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
              <span className="flex flex-wrap items-center gap-x-2.5 text-meta text-ink-muted">
                <KindName kind={task.executor} />
                <Ago iso={task.last_activity} />
                {task.turns > 1 ? <span>{t("task-turns", { count: task.turns })}</span> : null}
                <LastTurn task={task} />
              </span>
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

/** Reminders, watches and tasks are made by asking: the way to the agent, from where one looks at them. */
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

/** When a recurring one runs, in words. */
function rhythm(s: Schedule): string {
  const days = s.days.length ? s.days.map(weekdayLabel).join(", ") : tr("schedule-every-day");
  return `${days} · ${s.times.join(", ")}`;
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

function WatchPanel({ watch: w, onDone }: { watch: Watch; onDone: () => void }) {
  const t = useT();
  return (
    <SheetPanel
      icon={Radar}
      tone="watch"
      kind={t("act-kind-watch")}
      title={w.title}
      description={w.what}
      actions={
        <>
          <Link to="/watches/$watchId" params={{ watchId: w.id }} className={buttonVariants({ variant: "outline" })}>
            {t("watch-found")} <ArrowUpRight />
          </Link>
          <CancelWatch watch={w} onDone={onDone} />
        </>
      }
    >
      <Facts narrow className="text-body">
        <Fact term={t("watch-watches")}>
          <span className="flex flex-wrap gap-x-3">
            {w.kinds.map((k) => (
              <WatchKind key={k} kind={k} />
            ))}
          </span>
        </Fact>
        <Fact term={t("watch-rhythm")}>{t(w.once ? "watch-rhythm-once" : "watch-rhythm-every")}</Fact>
        <Fact term={t("act-for")}>{personName(w.owner)}</Fact>
        <Fact term={t("act-found")}>
          {w.triggered ? (
            <>
              {t("watch-triggered-count", { count: w.triggered })}
              {w.last_triggered_at ? (
                <span className="text-ink-muted">
                  {" · "}
                  <Ago iso={w.last_triggered_at} />
                </span>
              ) : null}
            </>
          ) : (
            t("watch-never-triggered")
          )}
        </Fact>
        <Fact term={t("act-started")}>{moment(w.created_at)}</Fact>
        {w.origin ? (
          <Fact term={t("watch-asked-in")}>
            <OriginLink origin={w.origin} />
          </Fact>
        ) : null}
      </Facts>
    </SheetPanel>
  );
}

function SchedulePanel({ schedule: s, onDone }: { schedule: Schedule; onDone: () => void }) {
  const t = useT();
  const canCancel = useCan("schedules:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelSchedule(s.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.schedules });
      notify(t("schedule-cancelled-notice"));
      onDone();
    },
  });
  return (
    <SheetPanel
      icon={AlarmClock}
      tone="ink"
      kind={t("act-kind-schedule")}
      title={s.title}
      description={s.instruction}
      actions={
        canCancel ? (
          <Confirm
            trigger={
              <Button variant="destructive">
                <Trash2 /> {t("schedule-cancel-confirm")}
              </Button>
            }
            title={t("schedule-cancel-title")}
            confirm={t("schedule-cancel-confirm")}
            onConfirm={() => cancel.mutateAsync()}
          >
            {t("schedule-cancel-description", { what: s.title })}
          </Confirm>
        ) : undefined
      }
    >
      <Facts narrow className="text-body">
        {s.next_due ? <Fact term={t("act-next")}>{moment(s.next_due)}</Fact> : null}
        <Fact term={t("watch-rhythm")}>{s.recurring ? rhythm(s) : t("schedule-once")}</Fact>
        <Fact term={t("act-for")}>{personName(s.owner)}</Fact>
        {s.origin ? (
          <Fact term={t("watch-asked-in")}>
            <OriginLink origin={s.origin} />
          </Fact>
        ) : null}
      </Facts>
    </SheetPanel>
  );
}
