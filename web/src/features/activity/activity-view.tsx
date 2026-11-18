/**
 * "Ongoing": everything the agent does for the household on its own, by where it stands: what waits
 * for an answer, what runs, what is planned, what it watches, what just ended. Each opens in a drawer.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  ArrowUpRight,
  Check,
  CircleHelp,
  Radar,
  Repeat,
  Send,
  ShieldQuestion,
  Trash2,
  Workflow,
  X,
} from "lucide-react";
import { useState } from "react";
import {
  api,
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
import { Chips } from "@/components/chips";
import { Confirm } from "@/components/confirm";
import { BrandTile, IconTile, OwnerMark, Pebble, type TileTone } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, Section } from "@/components/page";
import { Empty, Loading } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { TaskStatusMark } from "@/features/tasks/tasks";
import { WatchKind, watchBrand } from "@/features/watches/watches";
import { useT } from "@/i18n";
import { activeLocale, tr } from "@/i18n/runtime";
import { BrandMark, brandName, brandOf, KindMark, kindName } from "@/lib/brands";
import { dayLabel, hourMinute, moment } from "@/lib/dates";
import { weekdayLabel } from "@/lib/labels";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";

type Lane = "all" | "you" | "running" | "planned" | "watching";
type Opened = { kind: "task"; item: Task } | { kind: "watch"; item: Watch } | { kind: "schedule"; item: Schedule };

export function ActivityView() {
  const t = useT();
  const me = useMe();
  const confirmations = useQuery({ ...confirmationsQuery, enabled: useCan("messages:read") });
  const messages = useQuery({ ...messagesQuery, enabled: useCan("messages:read") });
  const tasks = useQuery({ ...tasksQuery, enabled: useCan("tasks:read") });
  const schedules = useQuery({ ...schedulesQuery, enabled: useCan("schedules:read") });
  const watches = useQuery({ ...watchesQuery, enabled: useCan("watches:read") });
  const canConfigure = useCan("config:manage");
  const [lane, setLane] = useState<Lane>("all");
  const [opened, setOpened] = useState<Opened | null>(null);

  const asks = confirmations.data ?? [];
  const questions = messages.data?.questions ?? [];
  const pending = messages.data?.pending ?? [];
  const running = tasks.data?.running ?? [];
  const recent = tasks.data?.recent ?? [];
  const planned = [...(schedules.data?.schedules ?? [])].sort((a, b) =>
    (a.next_due ?? "9").localeCompare(b.next_due ?? "9"),
  );
  const watching = watches.data?.watches ?? [];
  const lanes: { id: Lane; label: string; count: number }[] = [
    { id: "all", label: t("act-all"), count: 0 },
    { id: "you", label: t("act-you"), count: asks.length + questions.length + pending.length },
    { id: "running", label: t("act-running"), count: running.length },
    { id: "planned", label: t("act-planned"), count: planned.length },
    { id: "watching", label: t("act-watching"), count: watching.length },
  ];
  const shows = (id: Lane) => lane === "all" || lane === id;
  const waiting = asks.length + questions.length + pending.length;

  return (
    <div className="grid gap-10">
      <div>
        <PageHeader title={t("act-title")}>{t("act-lede", { assistant: me.assistant })}</PageHeader>
        <Chips label={t("act-title")} items={lanes} value={lane} onChange={setLane} />
      </div>

      {shows("you") && (waiting || lane === "you") ? (
        <Section title={t("act-you-title")} count={waiting}>
          {waiting ? (
            <ul className="grid gap-3 lg:grid-cols-2">
              {asks.map((c) => (
                <ConfirmationCard key={c.id} confirmation={c} />
              ))}
              {questions.map((m) => (
                <MessageCard key={m.id} message={m} icon={CircleHelp} tone="amber" state={t("act-awaits-reply")} />
              ))}
              {pending.map((m) => (
                <MessageCard key={m.id} message={m} icon={Send} tone="ink" state={t("act-on-its-way")} />
              ))}
            </ul>
          ) : (
            <Empty>{t("act-you-empty")}</Empty>
          )}
        </Section>
      ) : null}

      {shows("running") ? (
        <Section title={t("act-running-title")} count={running.length}>
          {tasks.isPending ? (
            <Loading lines={2} />
          ) : running.length ? (
            <ul className="grid gap-3 lg:grid-cols-2">
              {running.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    className="surface block w-full p-4 text-left"
                    onClick={() => setOpened({ kind: "task", item: task })}
                  >
                    <span className="flex items-start gap-4">
                      <IconTile icon={Workflow} tone="task" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[1.02rem] leading-snug font-medium text-ink">{task.title}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-x-2.5 text-[0.9rem] text-ink-muted">
                          <Executor name={task.executor} />
                          <span>
                            {t("task-since")} <Ago iso={task.started_at} />
                          </span>
                        </span>
                      </span>
                      {task.requested_by ? <Pebble name={task.requested_by.name} /> : null}
                    </span>
                    <span className="mt-3.5 block text-[0.9rem] text-ink">
                      {task.steps.at(-1) ?? t("home-task-starting")}
                    </span>
                    <span className="thread mt-2.5 block" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>{t("task-running-empty-hint")}</Empty>
          )}
        </Section>
      ) : null}

      {shows("planned") ? (
        <Section title={t("act-planned-title")} count={planned.length}>
          {schedules.isPending ? (
            <Loading lines={2} />
          ) : planned.length ? (
            <ol className="surface divide-y divide-rule overflow-hidden">
              {planned.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    className="grid w-full grid-cols-[minmax(4.5rem,auto)_1fr_auto] items-center gap-x-5 px-4 py-3.5 text-left hover:bg-paper-sunken/60"
                    onClick={() => setOpened({ kind: "schedule", item: s })}
                  >
                    <When iso={s.next_due} />
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{s.title}</span>
                      <span className="line-clamp-1 block text-[0.9rem] text-ink-muted">{s.instruction}</span>
                      {s.recurring ? (
                        <span className="mt-0.5 flex items-center gap-1.5 text-[0.85rem] text-ink-muted">
                          <Repeat className="size-3.5" aria-hidden="true" />
                          {rhythm(s)}
                        </span>
                      ) : null}
                    </span>
                    {s.owner ? <Pebble name={s.owner.name} /> : null}
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>{t("schedule-empty-hint", { assistant: me.assistant })}</Empty>
          )}
        </Section>
      ) : null}

      {shows("watching") ? (
        <Section title={t("act-watching-title")} count={watching.length}>
          {watches.isPending ? (
            <Loading lines={2} />
          ) : watching.length ? (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {watching.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    className="surface flex h-full w-full flex-col gap-3 p-4 text-left"
                    onClick={() => setOpened({ kind: "watch", item: w })}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <BrandTile brand={watchBrand(w.kinds[0])} />
                      <OwnerMark owner={w.owner} />
                    </span>
                    <span className="flex-1">
                      <span className="block text-[1.02rem] leading-snug font-medium text-ink">{w.title}</span>
                      <span className="mt-1 line-clamp-2 block text-[0.9rem] text-ink-muted">{w.what}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
                      {w.kinds.map((k) => (
                        <WatchKind key={k} kind={k} />
                      ))}
                      <span className={w.triggered ? "font-medium text-ember" : ""}>
                        {w.triggered ? t("watch-triggered-count", { count: w.triggered }) : t("watch-never-triggered")}
                      </span>
                    </span>
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

      {shows("running") && recent.length ? (
        <Section title={t("act-ended-title")}>
          <ul className="surface divide-y divide-rule overflow-hidden">
            {recent.slice(0, lane === "running" ? 20 : 5).map((task) => (
              <li key={task.id}>
                <button
                  type="button"
                  className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 px-4 py-3 text-left hover:bg-paper-sunken/60"
                  onClick={() => setOpened({ kind: "task", item: task })}
                >
                  <span className="min-w-0">
                    <span className="line-clamp-1 block text-ink">{task.title}</span>
                    <span className="flex flex-wrap items-center gap-x-2.5 text-[0.85rem] text-ink-muted">
                      <Executor name={task.executor} />
                      {task.ended_at ? <Ago iso={task.ended_at} /> : null}
                    </span>
                  </span>
                  <TaskStatusMark status={task.status} />
                </button>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <SideSheet open={Boolean(opened)} onOpenChange={(open) => !open && setOpened(null)}>
        {opened?.kind === "task" ? <TaskPanel task={opened.item} onDone={() => setOpened(null)} /> : null}
        {opened?.kind === "watch" ? <WatchPanel watch={opened.item} onDone={() => setOpened(null)} /> : null}
        {opened?.kind === "schedule" ? <SchedulePanel schedule={opened.item} onDone={() => setOpened(null)} /> : null}
      </SideSheet>
    </div>
  );
}

/** When a recurring one runs, in words. */
function rhythm(s: Schedule): string {
  const days = s.days.length ? s.days.map(weekdayLabel).join(", ") : tr("schedule-every-day");
  return `${days} · ${s.times.join(", ")}`;
}

/** The day over the hour: the left edge of a planned row, read like an agenda. */
function When({ iso }: { iso: string | null }) {
  if (!iso) return <span className="text-ink-faint">—</span>;
  // "Today", "Tomorrow", then a short date: the column stays narrow whatever the language
  const named = dayLabel(iso);
  const day = /\d/.test(named)
    ? new Intl.DateTimeFormat(activeLocale(), { weekday: "short", day: "numeric", month: "short" }).format(
        new Date(iso),
      )
    : named;
  return (
    <time dateTime={iso} className="grid">
      <span className="text-[0.8rem] text-ink-muted first-letter:uppercase">{day}</span>
      <span className="font-serif text-[1.35rem] leading-tight text-ink tabular">{hourMinute(iso)}</span>
    </time>
  );
}

function Executor({ name }: { name: string }) {
  const brand = brandOf(name);
  return (
    <span className="inline-flex items-center gap-1.5">
      {brand ? <BrandMark brand={brand} className="size-3.5" label={false} /> : null}
      {brand ? brandName(brand) : name}
    </span>
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
    <li className="surface flex gap-4 p-4">
      <IconTile icon={ShieldQuestion} tone="amber" />
      <div className="min-w-0 flex-1">
        <p className="text-[0.85rem] font-medium text-amber">{t("act-awaits-approval")}</p>
        <p className="mt-0.5 font-mono text-[0.95rem] text-ink">{c.tool}</p>
        {what ? <p className="mt-0.5 text-[0.9rem] text-ink-muted">{what}</p> : null}
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>{t("confirmation-for", { name: personName(c.person) })}</span>
          <span className="inline-flex items-center gap-1">
            <KindMark kind={c.origin.channel} className="size-3" label={false} />
            {kindName(c.origin.channel)}
          </span>
          <span>{t("confirmation-expires", { at: hourMinute(c.expires_at) })}</span>
        </p>
        {c.yours ? (
          <div className="mt-3 flex gap-2">
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
          </div>
        ) : (
          <p className="mt-2 text-[0.85rem] text-ink-muted">{t("confirmation-not-yours")}</p>
        )}
      </div>
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
  state: string;
}) {
  const t = useT();
  return (
    <li className="surface flex gap-4 p-4">
      <IconTile icon={icon} tone={tone} />
      <div className="min-w-0 flex-1">
        <p className="text-[0.85rem] font-medium text-ink-muted">{state}</p>
        <p className="mt-0.5 font-serif text-[1.1rem] leading-snug text-ink">{t("message-quoted", { text: m.text })}</p>
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>
            {m.requested_by
              ? t("message-from-to", { from: m.requested_by.name, to: m.to.name })
              : t("message-to", { to: m.to.name })}
          </span>
          {m.channel ? (
            <span className="inline-flex items-center gap-1">
              <KindMark kind={m.channel} className="size-3" label={false} />
              {kindName(m.channel)}
            </span>
          ) : null}
          <Ago iso={m.at} />
        </p>
      </div>
    </li>
  );
}

// -- the drawers ----------------------------------------------------------------------------------

function TaskPanel({ task, onDone }: { task: Task; onDone: () => void }) {
  const t = useT();
  const canCancel = useCan("tasks:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(task.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.tasks });
      notify(t("task-cancel-notice", { id: task.id }));
      onDone();
    },
  });
  return (
    <SheetPanel
      icon={Workflow}
      tone="task"
      kind={t("act-kind-task")}
      title={task.title}
      description={task.objective}
      actions={
        <>
          <Link to="/tasks/$taskId" params={{ taskId: task.id }} className={buttonVariants({ variant: "outline" })}>
            {t("act-open-page")} <ArrowUpRight />
          </Link>
          {canCancel && task.status === "running" ? (
            <Confirm
              trigger={
                <Button variant="ghost">
                  <X /> {t("task-cancel")}
                </Button>
              }
              title={t("task-cancel-title")}
              confirm={t("task-cancel")}
              onConfirm={() => cancel.mutateAsync()}
            >
              {t("task-cancel-description")}
            </Confirm>
          ) : null}
        </>
      }
    >
      <Facts narrow className="text-[0.95rem]">
        <Fact term={t("act-state")}>
          <TaskStatusMark status={task.status} />
        </Fact>
        <Fact term={t("act-by")}>
          <Executor name={task.executor} />
        </Fact>
        {task.requested_by ? <Fact term={t("act-for")}>{task.requested_by.name}</Fact> : null}
        <Fact term={t("act-started")}>{moment(task.started_at)}</Fact>
      </Facts>
      {task.steps.length ? (
        <div>
          <h3 className="mb-3 text-[1.15rem] text-ink">{t("task-story")}</h3>
          <ol className="grid gap-0">
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
                  <span className={cn("pb-3.5 text-[0.95rem]", last ? "text-ink" : "text-ink-muted")}>{step}</span>
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
      {task.result ? (
        <div>
          <h3 className="mb-2 text-[1.15rem] text-ink first-letter:uppercase">{t("task-result")}</h3>
          <p className="rounded-(--radius-surface) bg-paper-sunken px-4 py-3 text-[0.95rem] whitespace-pre-line text-ink">
            {task.result}
          </p>
        </div>
      ) : null}
      {task.error ? (
        <p className="rounded-(--radius-surface) bg-brick-soft px-4 py-3 text-[0.95rem] text-brick">{task.error}</p>
      ) : null}
    </SheetPanel>
  );
}

function WatchPanel({ watch: w, onDone }: { watch: Watch; onDone: () => void }) {
  const t = useT();
  const canCancel = useCan("watches:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelWatch(w.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.watches });
      notify(t("watch-cancelled-notice"));
      onDone();
    },
  });
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
          {canCancel ? (
            <Confirm
              trigger={
                <Button variant="ghost">
                  <Trash2 /> {t("watch-cancel")}
                </Button>
              }
              title={t("watch-cancel-title")}
              confirm={t("watch-cancel")}
              onConfirm={() => cancel.mutateAsync()}
            >
              {t("watch-cancel-description", { what: w.title })}
            </Confirm>
          ) : null}
        </>
      }
    >
      <Facts narrow className="text-[0.95rem]">
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
              <Button variant="outline">
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
      <Facts narrow className="text-[0.95rem]">
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
