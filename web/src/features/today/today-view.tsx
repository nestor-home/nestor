/**
 * "Today": the household as one picture, then what it asks of you, what the agent is doing, what
 * comes next and what happened. Everything opens where it is: a room, an event, a task.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  ArrowRight,
  BookMarked,
  ChevronDown,
  CircleAlert,
  Megaphone,
  MessageSquareText,
  MoonStar,
  Radar,
  Send,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  homeQuery,
  initiativeQuery,
  type JournalItem,
  journalLatestQuery,
  memoriesQuery,
  peopleQuery,
  satellitesQuery,
  schedulesQuery,
  type Task,
  tasksQuery,
  watchesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { IconTile, Pebble, type TileTone } from "@/components/marks";
import { Section } from "@/components/page";
import { Empty } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { useAgentPresence } from "@/features/agent/presence";
import { elsewhere, lineOf, type Mark, marksOf, nodeOf, type RoomNode, roomsOf } from "@/features/home/mind";
import { EventSheet } from "@/features/journal/event-sheet";
import { merge } from "@/features/journal/merge";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { useT } from "@/i18n";
import { activeLocale, tr } from "@/i18n/runtime";
import { BrandMark, brandName, brandOf } from "@/lib/brands";
import { hourMinute, moment, startOfToday } from "@/lib/dates";
import { say } from "@/lib/messages";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { RoomSheet } from "./room-sheet";
import { Scene } from "./scene";

function greeting(now: Date): string {
  const h = now.getHours();
  return tr(h < 5 ? "home-greeting-night" : h < 18 ? "home-greeting-day" : "home-greeting-evening");
}

const clock = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/** The thread page of an event's conversation (its session for records that predate conversations). */
const threadOf = (item: JournalItem) =>
  item.links.conversation ? { conversation: item.links.conversation } : { session: item.links.session ?? undefined };

/** A clock for what fades with time: every second just after a live event, else every minute. */
function useNow(busy: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), busy ? 1_000 : 60_000);
    return () => clearInterval(timer);
  }, [busy]);
  return now;
}

export function TodayView() {
  const t = useT();
  const me = useMe();
  const canPeople = useCan("people:read");
  const day = useQuery(journalLatestQuery({ from: startOfToday() }, 200));
  const people = useQuery({ ...peopleQuery, enabled: canPeople });
  const satellites = useQuery({ ...satellitesQuery, enabled: useCan("satellites:read") });
  const tasks = useQuery({ ...tasksQuery, enabled: useCan("tasks:read") });
  const home = useQuery({ ...homeQuery, enabled: useCan("home:read") });
  const { items: attention } = useAttention();
  const { state, latest, quiet } = useAgentPresence();

  // what arrives live joins the day at once
  const [live, setLive] = useState<JournalItem[]>([]);
  const [lastLive, setLastLive] = useState(0);
  useLiveItems((item) => {
    setLive((current) => [item, ...current].slice(0, 100));
    setLastLive(Date.now());
  });
  const now = useNow(Date.now() - lastLive < 30_000);
  const items = useMemo(() => merge(live, day.data?.items ?? []), [day.data, live]);
  const paired = satellites.data?.paired ?? [];
  const running = tasks.data?.running ?? [];
  const rooms = canPeople ? roomsOf({ people: people.data ?? [], satellites: paired, items, home: home.data }, 60) : [];
  const { away, homeNoRoom } = elsewhere(people.data ?? []);
  const marks = useMemo(() => marksOf(items), [items]);
  const date = new Date(now);
  const line = lineOf(
    latest,
    state,
    { tasks: running, troubled: attention.length, quietUntil: quiet?.active ? clock(quiet.to) : null },
    now,
  );
  const [open, setOpen] = useState<string | null>(null);
  const [event, setEvent] = useState<number | undefined>();
  const [all, setAll] = useState(false);
  const opened = rooms.find((r) => r.key === open) ?? null;

  return (
    <div className="grid gap-10 md:gap-12">
      <Scene
        now={date}
        date={new Intl.DateTimeFormat(activeLocale(), { weekday: "long", day: "numeric", month: "long" }).format(date)}
        greeting={t("home-hello", { greeting: greeting(date), name: me.account.person?.name ?? me.account.login })}
        agent={me.agent.name}
        state={state}
        stateLabel={t(`home-state-${state}`)}
        line={t(line.id, line.args)}
        rooms={rooms}
        home={homeNoRoom}
        away={away}
        focus={latest ? nodeOf(latest, paired) : null}
        onRoom={(r: RoomNode) => setOpen(r.key)}
      />

      {attention.length ? (
        <Section title={t("home-needs")} count={attention.length}>
          <ul className="grid gap-3 md:grid-cols-2">
            {(all ? attention : attention.slice(0, 4)).map((a) => (
              <li key={a.key} className="surface flex gap-4 p-4">
                <IconTile icon={a.icon} tone={a.tone === "error" ? "brick" : "amber"} />
                <div className="min-w-0 flex-1">
                  <p className="text-[1.02rem] leading-snug font-medium text-ink">{a.title}</p>
                  {a.detail ? <p className="mt-1 text-[0.92rem] text-ink-muted">{a.detail}</p> : null}
                  <Link {...a.link} className={cn(buttonVariants({ size: "sm" }), "mt-3")}>
                    {a.action}
                  </Link>
                </div>
              </li>
            ))}
          </ul>
          {attention.length > 4 ? (
            <button
              type="button"
              onClick={() => setAll((v) => !v)}
              aria-expanded={all}
              className="mt-3 inline-flex items-center gap-1.5 text-[0.92rem] font-medium text-ink-muted hover:text-ink"
            >
              <ChevronDown className={cn("size-4 transition-transform", all && "rotate-180")} aria-hidden="true" />
              {all ? t("today-needs-fewer") : t("today-needs-more", { count: attention.length - 4 })}
            </button>
          ) : null}
        </Section>
      ) : null}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:gap-12">
        <div className="grid content-start gap-10">
          <Now running={running} items={items} now={now} />
          <Day marks={marks} onEvent={setEvent} />
        </div>
        <div className="grid content-start gap-10">
          <Next />
          <Knows />
        </div>
      </div>

      <RoomSheet room={opened} items={items} onClose={() => setOpen(null)} />
      <EventSheet position={event} onClose={() => setEvent(undefined)} />
    </div>
  );
}

/** Tasks running and conversations under way. */
function Now({ running, items, now }: { running: Task[]; items: JournalItem[]; now: number }) {
  const t = useT();
  const talks = new Map<string, JournalItem>();
  for (const i of items) {
    const talk = i.links.conversation ?? i.links.session;
    if (i.kind !== "conversation" || !talk) continue;
    if (now - new Date(i.at).getTime() > 15 * 60_000) continue;
    if (!talks.has(talk)) talks.set(talk, i);
  }
  return (
    <Section title={t("home-now")} count={running.length + talks.size}>
      {running.length || talks.size ? (
        <ul className="grid gap-3">
          {running.map((task) => {
            const brand = brandOf(task.executor);
            return (
              <li key={task.id}>
                <Link to="/tasks/$taskId" params={{ taskId: task.id }} className="surface block p-4">
                  <span className="flex items-start gap-4">
                    <IconTile icon={Workflow} tone="task" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[1.02rem] leading-snug font-medium text-ink">{task.objective}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 text-[0.9rem] text-ink-muted">
                        {brand ? (
                          <span className="inline-flex items-center gap-1.5">
                            <BrandMark brand={brand} className="size-3.5" label={false} />
                            {brandName(brand)}
                          </span>
                        ) : null}
                        <span>{task.steps.at(-1) ?? t("home-task-starting")}</span>
                        <Ago iso={task.started_at} />
                      </span>
                    </span>
                  </span>
                  <span className="thread mt-4 block" aria-hidden="true" />
                </Link>
              </li>
            );
          })}
          {[...talks.values()].map((i) => (
            <li key={i.links.conversation ?? i.links.session}>
              <Link to="/journal" search={threadOf(i)} className="surface flex items-start gap-4 p-4">
                <IconTile icon={MessageSquareText} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-[1.02rem] font-medium text-ink">
                    {i.people.length
                      ? t("home-talking", { people: i.people.map((p) => p.name).join(", ") })
                      : t("home-talking-someone")}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-[0.92rem] text-ink-muted">
                    {i.detail_text || say(i)}
                  </span>
                </span>
                <span className="flex -space-x-1.5">
                  {i.people.map((p) => (
                    <Pebble key={p.id} name={p.name} />
                  ))}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>{t("home-nothing-now")}</Empty>
      )}
    </Section>
  );
}

const MARK: Record<Mark["kind"], { icon: LucideIcon; tone: TileTone }> = {
  conversation: { icon: MessageSquareText, tone: "ink" },
  delivery: { icon: Megaphone, tone: "ember" },
  task: { icon: Workflow, tone: "task" },
  watch: { icon: Radar, tone: "watch" },
  memory: { icon: BookMarked, tone: "sage" },
  problem: { icon: CircleAlert, tone: "brick" },
};

/** The day so far, newest first: each moment opens in place. */
function Day({ marks, onEvent }: { marks: Mark[]; onEvent: (position: number) => void }) {
  const t = useT();
  const latest = [...marks].reverse().slice(0, 9);
  const row =
    "group grid w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 px-4 py-3 text-left hover:bg-paper-sunken/60";
  return (
    <Section
      title={t("today-so-far")}
      aside={
        <Link to="/journal" className="inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink">
          {t("home-all-journal")} <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      }
    >
      {latest.length ? (
        <ol className="surface divide-y divide-rule overflow-hidden" aria-label={t("today-so-far")}>
          {latest.map((m) => {
            const text =
              m.kind === "conversation"
                ? m.people.length
                  ? t("home-moment-conversation", { people: m.people.map((p) => p.name).join(", "), count: m.count })
                  : t("home-moment-conversation-someone", { count: m.count })
                : m.item.detail_text && m.kind === "delivery"
                  ? m.item.detail_text
                  : say(m.item);
            const where = m.room ?? m.channels[0];
            const body = (
              <>
                <IconTile {...MARK[m.kind]} className="size-9" />
                <span className="min-w-0">
                  <span className="line-clamp-2 block text-ink">{text}</span>
                  {where ? <span className="block text-[0.85rem] text-ink-muted">{where}</span> : null}
                </span>
                <time dateTime={m.at} className="text-[0.9rem] text-ink-muted tabular">
                  {hourMinute(m.at)}
                </time>
              </>
            );
            return (
              <li key={m.key}>
                {m.kind === "conversation" ? (
                  <Link to="/journal" search={threadOf(m.item)} className={row}>
                    {body}
                  </Link>
                ) : (
                  <button type="button" className={row} onClick={() => onEvent(m.item.position)}>
                    {body}
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <Empty>{t("home-today-empty")}</Empty>
      )}
    </Section>
  );
}

interface Coming {
  key: string;
  at: string | null;
  icon: LucideIcon;
  tone: TileTone;
  text: string;
  hint?: string;
}

/** What comes next, soonest first: reminders, follow-ups, the quiet hours; then what it keeps watching. */
function Next() {
  const t = useT();
  const { quiet } = useAgentPresence();
  const schedules = useQuery({ ...schedulesQuery, enabled: useCan("schedules:read") });
  const watches = useQuery({ ...watchesQuery, enabled: useCan("watches:read") });
  const initiative = useQuery({ ...initiativeQuery, enabled: useCan("agent:read") });
  const coming: Coming[] = [
    ...(schedules.data?.schedules ?? [])
      .filter((s) => s.next_due)
      .map((s) => ({ key: s.id, at: s.next_due, icon: AlarmClock, tone: "ink" as const, text: s.instruction })),
    ...(initiative.data?.upcoming ?? []).map((u) => ({
      key: `${u.delivery}:${u.due_at}`,
      at: u.due_at,
      icon: Send,
      tone: "ember" as const,
      text: u.person
        ? t("today-follow-up", { person: u.person.name, channel: u.written_on.split(":")[0] ?? u.written_on })
        : t("today-follow-up-someone", { channel: u.written_on.split(":")[0] ?? u.written_on }),
      hint: t("home-upcoming-unless"),
    })),
  ]
    .sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""))
    .slice(0, 5);
  const watching = watches.data?.watches ?? [];
  return (
    <Section
      title={t("home-next")}
      aside={
        <Link to="/activity" className="inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink">
          {t("today-all-activity")} <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      }
    >
      <ul className="grid gap-2.5">
        {quiet ? (
          <li className="flex items-center gap-3 rounded-(--radius-surface) bg-paper-sunken px-4 py-3 text-[0.95rem] text-ink">
            <MoonStar className="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
            {quiet.active
              ? t("home-quiet-now", { until: clock(quiet.to) })
              : t("home-quiet-later", { from: clock(quiet.from), to: clock(quiet.to) })}
          </li>
        ) : null}
        {coming.map((c) => (
          <li key={c.key} className="surface flex items-start gap-3.5 p-3.5">
            <IconTile icon={c.icon} tone={c.tone} className="size-9" />
            <span className="min-w-0 flex-1">
              {c.at ? <span className="block text-[0.85rem] font-medium text-ember">{moment(c.at)}</span> : null}
              <span className="line-clamp-2 block text-ink">{c.text}</span>
              {c.hint ? <span className="block text-[0.85rem] text-ink-muted">{c.hint}</span> : null}
            </span>
          </li>
        ))}
        {watching.length ? (
          <li>
            <Link to="/activity" className="surface flex items-center gap-3.5 p-3.5">
              <IconTile icon={Radar} tone="watch" className="size-9" />
              <span className="min-w-0 flex-1">
                <span className="block text-ink">{t("today-watching", { count: watching.length })}</span>
                <span className="line-clamp-1 block text-[0.85rem] text-ink-muted">
                  {watching.map((w) => w.what).join(" · ")}
                </span>
              </span>
              <ArrowRight className="size-4 text-ink-faint" aria-hidden="true" />
            </Link>
          </li>
        ) : null}
        {!quiet && !coming.length && !watching.length ? <Empty>{t("today-nothing-next")}</Empty> : null}
      </ul>
    </Section>
  );
}

/** What it learnt lately, in its own words. */
function Knows() {
  const t = useT();
  const memories = useQuery({ ...memoriesQuery({}), enabled: useCan("memories:read") });
  const latest = [...(memories.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 3);
  if (!latest.length) return null;
  const today = startOfToday();
  return (
    <Section
      title={t("home-knows")}
      aside={
        <Link to="/memories" className="inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink">
          {t("home-all-memories")} <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      }
    >
      <ul className="grid gap-5">
        {latest.map((m) => (
          <li key={m.id}>
            <Link to="/memories" search={m.about ? { about: m.about.id } : {}} className="group flex gap-3">
              {m.about ? <Pebble name={m.about.name} className="mt-1" /> : null}
              <span className="min-w-0">
                <span className="block font-serif text-[1.15rem] leading-snug text-ink group-hover:underline">
                  {m.text}
                </span>
                <span className="mt-1 block text-[0.85rem] text-ink-muted">
                  {m.about ? `${m.about.name} · ` : ""}
                  {m.updated_at >= today ? (
                    t("home-learnt-today", { time: hourMinute(m.updated_at) })
                  ) : (
                    <Ago iso={m.updated_at} />
                  )}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
