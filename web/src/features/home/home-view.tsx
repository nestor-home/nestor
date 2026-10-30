/**
 * "Aujourd'hui": the agent first (its figure, what it says right now), then in one reading order
 * what it waits for from you, the house as it perceives it, what it is doing, what comes next,
 * its day so far and what it learnt. Plain lists, full titles, no decoration that says nothing.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  initiativeQuery,
  type JournalItem,
  journalLatestQuery,
  memoriesQuery,
  type Person,
  peopleQuery,
  satellitesQuery,
  tasksQuery,
  type UpcomingDelivery,
  watchesQuery,
} from "@/api";
import type { NestorController } from "@/character";
import { AgentFigure } from "@/components/agent-figure";
import { Ago } from "@/components/ago";
import { BowTie } from "@/components/bow-tie";
import { Dither } from "@/components/dither";
import { type Quiet, useAgentPresence } from "@/features/agent/presence";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { useT } from "@/i18n";
import { activeLocale, tr } from "@/i18n/runtime";
import { brandName, brandOf } from "@/lib/brands";
import { hourMinute, startOfToday } from "@/lib/dates";
import { say } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { elsewhere, lineOf, type Mark, marksOf, merge, nodeOf, type RoomNode, roomsOf } from "./mind";

function greeting(now = new Date()): string {
  const h = now.getHours();
  return tr(h < 5 ? "home-greeting-night" : h < 18 ? "home-greeting-day" : "home-greeting-evening");
}

/** Its own eye movements when nothing holds its attention (a constant: the controller lives once). */
const LIVE = { saccades: true };

/** The thread page of an event's conversation (its session for records that predate conversations). */
const threadOf = (item: JournalItem) =>
  item.links.conversation ? { conversation: item.links.conversation } : { session: item.links.session };

const clock = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/** A clock for what fades with time: every second just after a live event, else every minute. */
function useNow(busy: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), busy ? 1_000 : 60_000);
    return () => clearInterval(timer);
  }, [busy]);
  return now;
}

export function HomeView() {
  const t = useT();
  const me = useMe();
  const canTasks = useCan("tasks:read");
  const canWatches = useCan("watches:read");
  const canSatellites = useCan("satellites:read");
  const canPeople = useCan("people:read");
  const name = usePeopleNames();
  const day = useQuery(journalLatestQuery({ from: startOfToday() }, 200));
  const people = useQuery({ ...peopleQuery, enabled: canPeople });
  const satellites = useQuery({ ...satellitesQuery, enabled: canSatellites });
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const watches = useQuery({ ...watchesQuery, enabled: canWatches });
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
  const items = useMemo(() => merge(day.data?.items ?? [], live), [day.data, live]);
  const paired = satellites.data?.paired ?? [];
  const running = tasks.data?.running ?? [];
  const rooms = roomsOf({ people: people.data ?? [], satellites: paired, items });
  const { away } = elsewhere(people.data ?? []);
  const marks = useMemo(() => marksOf(items), [items]);
  const date = new Date(now);
  const line = lineOf(
    latest,
    state,
    { tasks: running, troubled: attention.length, quietUntil: quiet?.active ? clock(quiet.to) : null },
    name,
    now,
  );
  const focus = latest ? nodeOf(latest, paired) : null;
  const initiative = useQuery({ ...initiativeQuery, enabled: useCan("agent:read") });
  const later = initiative.data?.upcoming ?? [];
  const upcoming = (watches.data?.watches.length ?? 0) > 0 || Boolean(quiet) || later.length > 0;

  return (
    <div className="grid gap-16 md:gap-20">
      <Hero
        greeting={t("home-hello", { greeting: greeting(date), name: me.account.person_name ?? me.account.login })}
        date={new Intl.DateTimeFormat(activeLocale(), { weekday: "long", day: "numeric", month: "long" }).format(date)}
        agent={me.agent.name}
        state={state}
        line={t(line.id, line.args)}
        focus={focus}
      />

      {attention.length ? (
        <Band title={t("home-needs")} count={attention.length}>
          <ul className="grid gap-x-12 gap-y-5 md:grid-cols-2">
            {attention.map((a) => (
              <li key={a.key} className="grid grid-cols-[1.1rem_1fr] gap-x-3">
                <a.icon
                  className={cn("mt-1 size-4", a.tone === "error" ? "text-brick" : "text-amber")}
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-[1.02rem] leading-snug text-ink">{a.title}</p>
                  {a.detail ? <p className="mt-1 text-[0.92rem] text-ink-muted">{a.detail}</p> : null}
                  <Link
                    {...a.link}
                    className="mt-1.5 inline-flex items-center gap-1 text-[0.92rem] font-medium text-ember hover:underline"
                  >
                    {a.action} <ArrowRight className="size-3.5" aria-hidden="true" />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Band>
      ) : null}

      <div className={cn("grid gap-14 md:gap-10", upcoming ? "md:grid-cols-3" : "md:grid-cols-2")}>
        {canPeople ? <House rooms={rooms} away={away} focus={focus} /> : null}
        <Now running={running} items={items} now={now} />
        {upcoming ? <Next watches={watches.data?.watches ?? []} quiet={quiet} upcoming={later} /> : null}
      </div>

      <Today marks={marks} />
      <Knows />
    </div>
  );
}

/** The agent, alive, saying what it attends to; the greeting beside it. */
function Hero({
  greeting,
  date,
  agent,
  state,
  line,
  focus,
}: {
  greeting: string;
  date: string;
  agent: string;
  state: ReturnType<typeof useAgentPresence>["state"];
  line: string;
  focus: string | null;
}) {
  const t = useT();
  const controller = useRef<NestorController | null>(null);
  const [ready, setReady] = useState(false);
  // it looks toward what it attends to: the room of the latest event, if it is on the page
  useEffect(() => {
    if (!ready) return;
    const target = focus ? document.querySelector(`[data-focus="${CSS.escape(focus)}"]`) : null;
    if (target) controller.current?.lookAt(target);
    else controller.current?.center();
  }, [focus, ready]);
  return (
    <section
      aria-labelledby="hello"
      className="grid items-center gap-8 md:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]"
    >
      <div>
        <p className="mb-4 text-ink-muted first-letter:uppercase">{date}</p>
        <h1 id="hello" className="display-1 text-ink">
          {greeting}
        </h1>
      </div>
      <div className="flex items-center gap-4 md:justify-center md:gap-6">
        <Link
          to="/journal"
          aria-label={t("home-figure-label", { agent, state: t(`home-state-${state}`) })}
          className="relative shrink-0 rounded-full p-5 md:p-8"
        >
          {/* a soft dithered disc behind it, as on the site: atmosphere, never on its body */}
          <Dither
            shape="vignette"
            from={0.16}
            to={0}
            dot={3}
            className="pointer-events-none absolute inset-0 overflow-hidden rounded-full text-ink/[0.16]"
          />
          <span className="relative hidden md:block">
            <AgentFigure
              state={state}
              size="hero"
              ground
              live={LIVE}
              onReady={(c) => {
                controller.current = c;
                setReady(true);
              }}
            />
          </span>
          <span className="relative md:hidden">
            <AgentFigure state={state} size="lg" ground />
          </span>
        </Link>
        <p aria-live="polite" className="bubble-say mb-10 self-end md:mb-24">
          <span className="mb-0.5 block font-mono text-[0.68rem] text-ink-muted">
            {agent} · {t(`home-state-${state}`)}
          </span>
          {line}
        </p>
      </div>
      <div className="flex items-center gap-4 text-rule-strong md:col-span-2" aria-hidden="true">
        <span className="h-px flex-1 bg-rule" />
        <BowTie size={22} />
        <span className="h-px flex-1 bg-rule" />
      </div>
    </section>
  );
}

function Band({
  title,
  count,
  aside,
  children,
}: {
  title: string;
  count?: number;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const id = `band-${title.toLowerCase().replace(/[^\p{L}0-9]+/gu, "-")}`;
  return (
    <section aria-labelledby={id}>
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <h2 id={id} className="display-3 flex items-baseline gap-2.5 text-ink">
          {title}
          {count !== undefined ? <span className="font-sans text-sm text-ink-faint tabular">{count}</span> : null}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Rooms with who is there; who is away. */
function House({ rooms, away, focus }: { rooms: RoomNode[]; away: Person[]; focus: string | null }) {
  const t = useT();
  return (
    <Band title={t("home-house")}>
      <ul className="grid gap-4">
        {rooms.map((r) => {
          const offline = r.satellites.filter((s) => s.connected === false).length;
          return (
            <li key={r.key} data-focus={r.key}>
              <Link to="/journal" search={{ room: r.room }} className="group block">
                <span
                  className={cn(
                    "text-[1.05rem] text-ink group-hover:underline",
                    focus === r.key && "underline decoration-ember decoration-2 underline-offset-4",
                  )}
                >
                  {capital(r.room)}
                </span>
                <span className="mt-0.5 block text-[0.92rem] text-ink-muted">
                  {r.people.length ? r.people.map((p) => p.name).join(", ") : t("home-room-nobody")}
                  {offline ? <span className="text-amber"> · {t("home-room-offline", { count: offline })}</span> : null}
                </span>
              </Link>
            </li>
          );
        })}
        {away.length ? (
          <li>
            <Link to="/people" className="group block">
              <span className="text-[1.05rem] text-ink group-hover:underline">{t("home-away")}</span>
              <span className="mt-0.5 block text-[0.92rem] text-ink-muted">{away.map((p) => p.name).join(", ")}</span>
            </Link>
          </li>
        ) : null}
      </ul>
    </Band>
  );
}

/** Tasks running and conversations under way, full titles. */
function Now({
  running,
  items,
  now,
}: {
  running: { id: string; objective: string; executor: string; steps: string[]; started_at: string }[];
  items: JournalItem[];
  now: number;
}) {
  const t = useT();
  const name = usePeopleNames();
  const talks = new Map<string, JournalItem>();
  for (const i of items) {
    const talk = i.links.conversation ?? i.links.session;
    if (i.kind !== "conversation" || !talk) continue;
    if (now - new Date(i.at).getTime() > 15 * 60_000) continue;
    if (!talks.has(talk)) talks.set(talk, i);
  }
  return (
    <Band title={t("home-now")}>
      {running.length || talks.size ? (
        <ul className="grid gap-5">
          {running.map((task) => {
            const brand = brandOf(task.executor);
            return (
              <li key={task.id}>
                <Link to="/tasks/$taskId" params={{ taskId: task.id }} className="group block">
                  <span className="text-[1.05rem] leading-snug text-ink group-hover:underline">{task.objective}</span>
                  <span className="mt-1 block text-[0.92rem] text-ink-muted">
                    {task.steps.at(-1) ?? t("home-task-starting")}
                    {brand ? ` · ${brandName(brand)}` : ""} · <Ago iso={task.started_at} />
                  </span>
                </Link>
              </li>
            );
          })}
          {[...talks.values()].map((i) => (
            <li key={i.links.conversation ?? i.links.session}>
              <Link to="/journal" search={threadOf(i)} className="group block">
                <span className="text-[1.05rem] text-ink group-hover:underline">
                  {i.people.length
                    ? t("home-talking", { people: i.people.map((p) => name(p)).join(", ") })
                    : t("home-talking-someone")}
                </span>
                <span className="mt-1 block text-[0.92rem] text-ink-muted">{i.detail || say(i)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-ink-muted">{t("home-nothing-now")}</p>
      )}
    </Band>
  );
}

/** What comes next: the quiet hours, the watches waiting. */
function Next({
  watches,
  quiet,
  upcoming,
}: {
  watches: { id: string; what: string; last_triggered_at: string | null }[];
  quiet: Quiet | null;
  upcoming: UpcomingDelivery[];
}) {
  const t = useT();
  return (
    <Band title={t("home-next")}>
      <ul className="grid gap-5">
        {quiet ? (
          <li>
            <span className="text-[1.05rem] text-ink">
              {quiet.active
                ? t("home-quiet-now", { until: clock(quiet.to) })
                : t("home-quiet-later", { from: clock(quiet.from), to: clock(quiet.to) })}
            </span>
          </li>
        ) : null}
        {upcoming.map((u) => (
          <li key={`${u.delivery}:${u.due_at}`}>
            <Link to="/journal" search={{ q: u.delivery }} className="group block">
              <span className="text-[1.05rem] leading-snug text-ink group-hover:underline">
                {u.person
                  ? t("home-upcoming", {
                      person: u.person.name,
                      channel: u.written_on.split(":")[0] ?? u.written_on,
                      time: hourMinute(u.due_at),
                    })
                  : t("home-upcoming-someone", {
                      channel: u.written_on.split(":")[0] ?? u.written_on,
                      time: hourMinute(u.due_at),
                    })}
              </span>
              <span className="mt-1 block text-[0.92rem] text-ink-muted">{t("home-upcoming-unless")}</span>
            </Link>
          </li>
        ))}
        {watches.map((w) => (
          <li key={w.id}>
            <Link to="/watches/$watchId" params={{ watchId: w.id }} className="group block">
              <span className="text-[1.05rem] leading-snug text-ink group-hover:underline">{w.what}</span>
              {w.last_triggered_at ? (
                <span className="mt-1 block text-[0.92rem] text-ink-muted">
                  {t("home-watch-triggered")} <Ago iso={w.last_triggered_at} />
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </Band>
  );
}

const MARK_TONE: Record<Mark["kind"], string> = {
  conversation: "bg-ink",
  delivery: "bg-ember",
  task: "bg-kind-task",
  watch: "bg-kind-watch",
  memory: "bg-sage",
  problem: "bg-brick",
};

/** Today's notable moments, newest first, each a way into the journal. */
function Today({ marks }: { marks: Mark[] }) {
  const t = useT();
  const name = usePeopleNames();
  const latest = [...marks].reverse().slice(0, 8);
  return (
    <Band
      title={t("home-today")}
      aside={
        <Link to="/journal" className="inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink">
          {t("home-all-journal")} <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      }
    >
      {latest.length ? (
        <ol className="grid" aria-label={t("home-today")}>
          {latest.map((m) => {
            const text =
              m.kind === "conversation"
                ? m.people.length
                  ? t("home-moment-conversation", { people: m.people.map((p) => name(p)).join(", "), count: m.count })
                  : t("home-moment-conversation-someone", { count: m.count })
                : m.item.detail && m.kind === "delivery"
                  ? m.item.detail
                  : say(m.item);
            return (
              <li key={m.key}>
                <Link
                  to="/journal"
                  search={m.kind === "conversation" ? threadOf(m.item) : { event: m.item.id }}
                  className="group grid grid-cols-[3.2rem_0.6rem_1fr] items-baseline gap-x-3 py-2.5"
                >
                  <time dateTime={m.at} className="font-mono text-[0.85rem] text-ink-muted tabular">
                    {hourMinute(m.at)}
                  </time>
                  <span
                    aria-hidden="true"
                    className={cn("size-2 translate-y-[-1px] rounded-full", MARK_TONE[m.kind])}
                  />
                  <span className="min-w-0 text-ink group-hover:underline">
                    {text}
                    {m.kind === "delivery" && (m.room || m.channels[0]) ? (
                      <span className="text-ink-muted"> · {m.room ?? m.channels[0]}</span>
                    ) : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-ink-muted">{t("home-today-empty")}</p>
      )}
    </Band>
  );
}

/** What it learnt: the latest memories, today's first. */
function Knows() {
  const t = useT();
  const name = usePeopleNames();
  const memories = useQuery({ ...memoriesQuery({}), enabled: useCan("memories:read") });
  const latest = [...(memories.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 4);
  if (!latest.length) return null;
  const today = startOfToday();
  return (
    <Band
      title={t("home-knows")}
      aside={
        <Link to="/memories" className="inline-flex items-center gap-1 text-[0.92rem] text-ink-muted hover:text-ink">
          {t("home-all-memories")} <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      }
    >
      <ul className="grid gap-x-12 gap-y-6 md:grid-cols-2">
        {latest.map((m) => (
          <li key={m.id}>
            <Link to="/memories" search={m.about ? { about: m.about } : {}} className="group block">
              <span className="block font-serif text-[1.2rem] leading-snug text-ink group-hover:underline">
                {m.text}
              </span>
              <span className="mt-1.5 block text-[0.88rem] text-ink-muted">
                {m.about ? `${name(m.about)} · ` : ""}
                {m.updated_at >= today ? (
                  t("home-learnt-today", { time: hourMinute(m.updated_at) })
                ) : (
                  <Ago iso={m.updated_at} />
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Band>
  );
}
