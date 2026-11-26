/**
 * "Today": the household as one picture, then what it asks of you, what the agent is doing, what
 * comes next and what happened. Everything opens where it is: a room, an event, a task.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
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
import { useMemo, useState } from "react";
import {
  homeQuery,
  initiativeQuery,
  type JournalItem,
  journalLatestQuery,
  memoriesQuery,
  type Person,
  peopleQuery,
  type Satellite,
  satellitesQuery,
  schedulesQuery,
  type Task,
  tasksQuery,
  watchesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, MoreLink, OpenArrow } from "@/components/card";
import { Avatar, IconTile, type TileTone } from "@/components/marks";
import { RowList, Section } from "@/components/page";
import { Empty } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { useAgentPresence } from "@/features/agent/presence";
import { EventSheet } from "@/features/journal/event-sheet";
import { merge } from "@/features/journal/merge";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { TaskCardBody } from "@/features/tasks/parts";
import { elsewhere, lineOf, type Mark, marksOf, nodeOf, type RoomNode, roomsOf } from "@/features/today/mind";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { kindName } from "@/lib/brands";
import { hourMinute, longDate, moment, startOfToday } from "@/lib/dates";
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

/** A clock for what fades with time: every second just after a live event, else every minute. Only the parts
 * that read the time hold it, so the rest of the page does not render with it. */
const useClock = (lastLive: number) => useNow(Date.now() - lastLive < 30_000 ? 1_000 : 60_000);

export function TodayView() {
  const t = useT();
  const canPeople = useCan("people:read");
  const from = startOfToday();
  const day = useQuery(journalLatestQuery({ from }, 200));
  const people = useQuery({ ...peopleQuery, enabled: canPeople });
  const satellites = useQuery({ ...satellitesQuery, enabled: useCan("satellites:read") });
  const tasks = useQuery({ ...tasksQuery, enabled: useCan("tasks:read") });
  const home = useQuery({ ...homeQuery, enabled: useCan("home:read") });
  const { items: attention } = useAttention();

  // what arrives live joins the day at once
  const [live, setLive] = useState<JournalItem[]>([]);
  const [lastLive, setLastLive] = useState(0);
  useLiveItems((item) => {
    setLive((current) => [item, ...current].slice(0, 100));
    setLastLive(Date.now());
  });
  // what arrived live before midnight leaves the day with it
  const items = useMemo(
    () =>
      merge(
        live.filter((i) => Date.parse(i.at) >= Date.parse(from)),
        day.data?.items ?? [],
      ),
    [day.data, live, from],
  );
  const running = (tasks.data?.tasks ?? []).filter((task) => task.state === "working");
  const rooms = useMemo(
    () =>
      canPeople
        ? roomsOf({ people: people.data ?? [], satellites: satellites.data?.paired ?? [], items, home: home.data }, 60)
        : [],
    [canPeople, people.data, satellites.data, items, home.data],
  );
  const marks = useMemo(() => marksOf(items), [items]);
  const [open, setOpen] = useState<string | null>(null);
  const [event, setEvent] = useState<number | undefined>();
  const [all, setAll] = useState(false);
  const opened = rooms.find((r) => r.key === open) ?? null;

  return (
    <div className="grid gap-10 md:gap-12">
      <Hello
        lastLive={lastLive}
        rooms={rooms}
        people={people.data}
        paired={satellites.data?.paired}
        running={running}
        troubled={attention.length}
        onRoom={(r: RoomNode) => setOpen(r.key)}
      />

      {attention.length ? (
        <Section title={t("home-needs")} count={attention.length}>
          <ul className="grid gap-3 md:grid-cols-2">
            {(all ? attention : attention.slice(0, 4)).map((a) => (
              <li key={a.key} className="surface p-4">
                <CardHead
                  mark={<IconTile icon={a.icon} tone={a.tone === "error" ? "brick" : "amber"} />}
                  title={a.title}
                  line={a.detail}
                >
                  <Link {...a.link} className={buttonVariants({ size: "sm" })}>
                    {a.action}
                  </Link>
                </CardHead>
              </li>
            ))}
          </ul>
          {attention.length > 4 ? (
            <button
              type="button"
              onClick={() => setAll((v) => !v)}
              aria-expanded={all}
              className="mt-3 inline-flex items-center gap-1.5 text-body font-medium text-ink-muted hover:text-ink"
            >
              <ChevronDown className={cn("size-4 transition-transform", all && "rotate-180")} aria-hidden="true" />
              {all ? t("today-needs-fewer") : t("today-needs-more", { count: attention.length - 4 })}
            </button>
          ) : null}
        </Section>
      ) : null}

      <div className="grid gap-10 @4xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] @4xl:gap-12">
        <div className="grid content-start gap-10">
          <Now running={running} items={items} lastLive={lastLive} />
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

/** The scene: the hour's sky, the greeting, the agent's line, and who is in which room. */
function Hello({
  lastLive,
  rooms,
  people,
  paired = [],
  running,
  troubled,
  onRoom,
}: {
  lastLive: number;
  rooms: RoomNode[];
  people: Person[] | undefined;
  paired: Satellite[] | undefined;
  running: Task[];
  troubled: number;
  onRoom: (room: RoomNode) => void;
}) {
  const t = useT();
  const me = useMe();
  const { state, latest, quiet } = useAgentPresence();
  const now = useClock(lastLive);
  const { away, homeNoRoom } = useMemo(() => elsewhere(people ?? []), [people]);
  const line = lineOf(
    latest,
    state,
    { tasks: running, troubled, quietUntil: quiet?.active ? clock(quiet.to) : null },
    now.getTime(),
  );
  return (
    <Scene
      now={now}
      date={longDate(now)}
      greeting={t("home-hello", { greeting: greeting(now), name: me.account.person?.name ?? me.account.login })}
      agent={me.agent.name}
      state={state}
      stateLabel={t(`home-state-${state}`)}
      line={t(line.id, line.args)}
      rooms={rooms}
      home={homeNoRoom}
      away={away}
      focus={latest ? nodeOf(latest, paired) : null}
      onRoom={onRoom}
    />
  );
}

/** Tasks running and conversations under way. */
function Now({ running, items, lastLive }: { running: Task[]; items: JournalItem[]; lastLive: number }) {
  const t = useT();
  const now = useClock(lastLive).getTime();
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
          {running.map((task) => (
            <li key={task.id}>
              <Link to="/tasks/$taskId" params={{ taskId: task.id }} className="surface block p-4">
                <TaskCardBody task={task} />
              </Link>
            </li>
          ))}
          {[...talks.values()].map((i) => (
            <li key={i.links.conversation ?? i.links.session}>
              <Link to="/journal" search={threadOf(i)} className="surface block p-4">
                <CardHead
                  mark={<IconTile icon={MessageSquareText} />}
                  title={
                    i.people.length
                      ? t("home-talking", { people: i.people.map((p) => p.name).join(", ") })
                      : t("home-talking-someone")
                  }
                  line={<span className="line-clamp-2">{i.detail_text || say(i)}</span>}
                  aside={
                    <span className="flex -space-x-1.5">
                      {i.people.map((p) => (
                        <Avatar key={p.id} name={p.name} />
                      ))}
                    </span>
                  }
                />
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
    <Section title={t("today-so-far")} aside={<MoreLink to="/journal">{t("home-all-journal")}</MoreLink>}>
      {latest.length ? (
        <RowList ordered aria-label={t("today-so-far")}>
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
                <IconTile {...MARK[m.kind]} size="sm" />
                <span className="min-w-0">
                  <span className="line-clamp-2 block text-ink">{text}</span>
                  {where ? <span className="block text-meta text-ink-muted">{where}</span> : null}
                </span>
                <time dateTime={m.at} className="text-body text-ink-muted tabular">
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
        </RowList>
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
      .map((s) => ({ key: s.id, at: s.next_due, icon: AlarmClock, tone: "ink" as const, text: s.title })),
    ...(initiative.data?.upcoming ?? []).map((u) => ({
      key: `${u.delivery}:${u.due_at}`,
      at: u.due_at,
      icon: Send,
      tone: "ember" as const,
      text: u.person
        ? t("today-follow-up", { person: u.person.name, channel: kindName(u.written_on.split(":")[0] ?? "") })
        : t("today-follow-up-someone", { channel: kindName(u.written_on.split(":")[0] ?? "") }),
      hint: t("home-upcoming-unless"),
    })),
  ]
    .sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""))
    .slice(0, 5);
  const watching = watches.data?.watches ?? [];
  return (
    <Section title={t("home-next")} aside={<MoreLink to="/activity">{t("today-all-activity")}</MoreLink>}>
      <ul className="grid gap-2.5">
        {quiet ? (
          <li className="flex items-center gap-3 rounded-(--radius-surface) bg-paper-sunken px-4 py-3 text-body text-ink">
            <MoonStar className="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
            {quiet.active
              ? t("home-quiet-now", { until: clock(quiet.to) })
              : t("home-quiet-later", { from: clock(quiet.from), to: clock(quiet.to) })}
          </li>
        ) : null}
        {coming.map((c) => (
          <li key={c.key} className="surface p-3.5">
            <CardHead
              mark={<IconTile icon={c.icon} tone={c.tone} size="sm" />}
              title={<span className="line-clamp-2">{c.text}</span>}
              line={
                <>
                  {c.at ? <span className="font-medium text-ember">{moment(c.at)}</span> : null}
                  {c.at && c.hint ? " · " : null}
                  {c.hint}
                </>
              }
            />
          </li>
        ))}
        {watching.length ? (
          <li>
            <Link to="/activity" className="group surface block p-3.5">
              <CardHead
                mark={<IconTile icon={Radar} tone="watch" size="sm" />}
                title={t("today-watching", { count: watching.length })}
                line={<span className="line-clamp-1">{watching.map((w) => w.title).join(" · ")}</span>}
                aside={<OpenArrow />}
              />
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
    <Section title={t("home-knows")} aside={<MoreLink to="/memories">{t("home-all-memories")}</MoreLink>}>
      <ul className="grid gap-5">
        {latest.map(({ place: { person }, ...m }) => (
          <li key={m.id}>
            <Link to="/memories" search={person ? { about: person.id } : {}} className="group flex gap-3">
              {person ? <Avatar name={person.name} className="mt-1" /> : null}
              <span className="min-w-0">
                <span className="block title-sub text-ink group-hover:underline">{m.text}</span>
                <span className="mt-1 block text-meta text-ink-muted">
                  {person ? `${person.name} · ` : ""}
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
