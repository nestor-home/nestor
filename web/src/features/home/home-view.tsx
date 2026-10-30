/**
 * "Aujourd'hui": looking into the agent's mind right now. One centrepiece (what it perceives and
 * reaches, live), then tight bands: what it does and intends, its day, what needs a person (only
 * when something does), and what it learnt.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookMarked, Moon, Radar, Workflow } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  configQuery,
  connectionsQuery,
  type JournalItem,
  journalLatestQuery,
  memoriesQuery,
  peopleQuery,
  satellitesQuery,
  systemQuery,
  tasksQuery,
  watchesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { buttonVariants } from "@/components/ui/button";
import { useAgentPresence } from "@/features/agent/presence";
import { useAttention } from "@/features/shell/attention";
import { useLiveItems } from "@/features/shell/live";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, brandOf, KindMark } from "@/lib/brands";
import { hourMinute, startOfToday } from "@/lib/dates";
import { say } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { AgentMind } from "./agent-mind";
import { DayRibbon } from "./day-ribbon";
import { elsewhere, isQuiet, lineOf, marksOf, merge, nodeOf, type Reach, roomsOf } from "./mind";

function greeting(now = new Date()): string {
  const h = now.getHours();
  return tr(h < 5 ? "home-greeting-night" : h < 18 ? "home-greeting-day" : "home-greeting-evening");
}

/**
 * A clock for what fades with time: every second while something just happened (the agent's state,
 * glows), every minute otherwise (the present on the day's ribbon).
 */
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
  const canConnections = useCan("connections:read");
  const canPeople = useCan("people:read");
  const canConfig = useCan("config:manage");
  const today = startOfToday();
  const day = useQuery(journalLatestQuery({ from: today }, 200));
  const people = useQuery({ ...peopleQuery, enabled: canPeople });
  const satellites = useQuery({ ...satellitesQuery, enabled: canSatellites });
  const system = useQuery({ ...systemQuery, enabled: canSatellites });
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const watches = useQuery({ ...watchesQuery, enabled: canWatches });
  const connections = useQuery({ ...connectionsQuery, enabled: canConnections });
  // quiet hours are a setting of the file: read when the account may read it, never guessed
  const config = useQuery({ ...configQuery, enabled: canConfig });
  const { items: attention } = useAttention();

  // what arrives live joins the day, makes the agent ripple and its node glow
  const [live, setLive] = useState<JournalItem[]>([]);
  const [pulses, setPulses] = useState<Record<string, number>>({});
  const [lastLive, setLastLive] = useState(0);
  const now = useNow(Date.now() - lastLive < 30_000);
  const paired = satellites.data?.paired ?? [];
  useLiveItems((item) => {
    setLive((current) => [item, ...current].slice(0, 100));
    setLastLive(Date.now());
    const node = nodeOf(item, paired);
    setPulses((current) => ({ ...current, agent: Date.now(), ...(node ? { [node]: Date.now() } : {}) }));
  });
  const items = useMemo(() => merge(day.data?.items ?? [], live), [day.data, live]);

  const running = tasks.data?.running ?? [];
  const { state, latest, quiet } = useAgentPresence();
  const name = usePeopleNames();
  const rooms = roomsOf({ people: people.data ?? [], satellites: paired, items });
  const { away } = elsewhere(people.data ?? []);
  const reach: Reach | null =
    canSatellites || canTasks || canWatches || canConnections
      ? {
          channels: (system.data?.components ?? []).filter((c) => c.slot === "channel"),
          tasks: running,
          watches: watches.data?.watches ?? [],
          connections: connections.data ?? [],
        }
      : null;
  const initiative = (config.data?.document.initiative ?? null) as Record<string, unknown> | null;
  const clock = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  const line = lineOf(
    latest,
    state,
    { tasks: running, troubled: attention.length, quietUntil: quiet ? clock(quiet.to) : null },
    name,
    now,
  );
  const marks = useMemo(() => marksOf(items), [items]);
  const date = new Date(now);

  return (
    <div className="grid gap-12 [&>*]:min-w-0">
      <div className="grid gap-5 [&>*]:min-w-0">
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <h1 className="text-[1.9rem] leading-[1.05] font-normal sm:text-[2.3rem]">
            {t("home-hello", { greeting: greeting(date), name: me.account.person_name ?? me.account.login })}
          </h1>
          <p className="font-mono text-xs text-ink-muted">
            {t("home-today", {
              conversations: marks.filter((m) => m.kind === "conversation").length,
              spoken: marks.filter((m) => m.kind === "delivery").length,
            })}
          </p>
        </header>
        <AgentMind
          agent={me.agent}
          state={state}
          calm={attention.length === 0}
          rooms={rooms}
          away={away}
          reach={reach}
          pulses={pulses}
          now={now}
          line={t(line.id, line.args)}
          focus={latest ? nodeOf(latest, paired) : null}
        />
      </div>

      <Band title={t("home-doing")}>
        <div className="grid gap-8 md:grid-cols-2">
          <Doing items={items} running={running} now={now} />
          <Intends watches={reach?.watches ?? []} quiet={quiet} mainRoom={initiative?.main_room} now={date} />
        </div>
      </Band>

      <Band
        title={t("home-day")}
        aside={
          <Link
            to="/journal"
            className="inline-flex items-center gap-1 font-mono text-xs text-ink-muted hover:text-ink"
          >
            {t("home-all-journal")} <ArrowRight className="size-3" aria-hidden="true" />
          </Link>
        }
      >
        <DayRibbon marks={marks} quiet={quiet} now={date} />
      </Band>

      {attention.length ? (
        <Band title={t("home-attention-title")} count={attention.length}>
          <ul className="divide-y divide-rule border-y border-rule">
            {attention.map((a) => (
              <li key={a.key} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                <a.icon
                  className={cn("size-4 shrink-0", a.tone === "error" ? "text-brick" : "text-amber")}
                  aria-hidden="true"
                />
                <p className="min-w-0 flex-1 text-sm text-ink">
                  {a.title}
                  {a.detail ? <span className="text-ink-muted"> — {a.detail}</span> : null}
                </p>
                <Link {...a.link} className={buttonVariants({ variant: "outline", size: "sm" })}>
                  {a.action}
                </Link>
              </li>
            ))}
          </ul>
        </Band>
      ) : null}

      <Knows />
    </div>
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
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 id={id} className="flex items-baseline gap-3 font-serif text-[1.35rem] font-normal text-ink">
          {title}
          {count !== undefined ? <span className="font-mono text-xs text-ink-faint tabular">{count}</span> : null}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Now: the tasks running and the conversations under way. */
function Doing({ items, running, now }: { items: JournalItem[]; running: Reach["tasks"]; now: number }) {
  const t = useT();
  const name = usePeopleNames();
  const recent = new Map<string, JournalItem>();
  for (const i of items) {
    if (i.kind !== "conversation" || !i.links.session) continue;
    if (now - new Date(i.at).getTime() > 15 * 60_000) continue;
    if (!recent.has(i.links.session)) recent.set(i.links.session, i);
  }
  const talks = [...recent.values()];
  return (
    <div>
      <p className="label-mono mb-2">{t("home-now")}</p>
      {running.length || talks.length ? (
        <ul className="grid gap-3">
          {running.map((task) => {
            const brand = brandOf(task.executor);
            return (
              <li key={task.id}>
                <Link
                  to="/tasks/$taskId"
                  params={{ taskId: task.id }}
                  className="group grid grid-cols-[1rem_1fr] gap-x-2"
                >
                  <Workflow className="mt-0.5 size-4 text-kind-task" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-ink group-hover:text-ember">{task.objective}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 font-mono text-[0.68rem] text-ink-muted">
                      {brand ? <BrandMark brand={brand} className="size-3" label={false} /> : null}
                      <span className="truncate">{task.steps.at(-1) ?? t("home-task-starting")}</span>
                      <span className="shrink-0">
                        · <Ago iso={task.started_at} />
                      </span>
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
          {talks.map((i) => (
            <li key={i.links.session}>
              <Link
                to="/journal"
                search={{ session: i.links.session }}
                className="group grid grid-cols-[1rem_1fr] gap-x-2"
              >
                <KindMark kind={i.channels[0] ?? "voice"} className="mt-0.5 size-4 text-ink" label={false} />
                <span className="min-w-0">
                  <span className="block truncate text-sm text-ink group-hover:text-ember">
                    {i.people.length
                      ? t("home-talking", {
                          people: i.people.map((p) => name(p)).join(", "),
                          where: i.room ?? i.channels[0] ?? "",
                        })
                      : t("home-talking-someone", { where: i.room ?? i.channels[0] ?? "" })}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-[0.68rem] text-ink-muted">
                    {i.detail || say(i)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-muted">{t("home-nothing-now")}</p>
      )}
    </div>
  );
}

/** Next: what it waits for, and when it will keep quiet. */
function Intends({
  watches,
  quiet,
  mainRoom,
  now,
}: {
  watches: Reach["watches"];
  quiet: { from: number; to: number } | null;
  mainRoom: unknown;
  now: Date;
}) {
  const t = useT();
  const minute = now.getHours() * 60 + now.getMinutes();
  const clock = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  return (
    <div>
      <p className="label-mono mb-2">{t("home-next")}</p>
      <ul className="grid gap-3">
        {quiet ? (
          <li className="grid grid-cols-[1rem_1fr] gap-x-2">
            <Moon className="mt-0.5 size-4 text-ink-muted" aria-hidden="true" />
            <span className="text-sm text-ink">
              {isQuiet(quiet, minute)
                ? t("home-quiet-now", { until: clock(quiet.to) })
                : t("home-quiet-later", { from: clock(quiet.from), to: clock(quiet.to) })}
              {typeof mainRoom === "string" ? (
                <span className="block font-mono text-[0.68rem] text-ink-muted">
                  {t("home-main-room", { room: mainRoom })}
                </span>
              ) : null}
            </span>
          </li>
        ) : null}
        {watches.slice(0, 4).map((w) => (
          <li key={w.id}>
            <Link to="/watches/$watchId" params={{ watchId: w.id }} className="group grid grid-cols-[1rem_1fr] gap-x-2">
              <Radar className="mt-0.5 size-4 text-kind-watch" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block truncate text-sm text-ink group-hover:text-ember">{w.what}</span>
                <span className="mt-0.5 block font-mono text-[0.68rem] text-ink-muted">
                  {w.last_triggered_at ? (
                    <>
                      {t("home-watch-triggered")} <Ago iso={w.last_triggered_at} />
                    </>
                  ) : (
                    t("home-watch-waiting", { sources: w.kinds.join(", ") || "—" })
                  )}
                </span>
              </span>
            </Link>
          </li>
        ))}
        {!quiet && !watches.length ? <li className="text-sm text-ink-muted">{t("home-nothing-next")}</li> : null}
      </ul>
    </div>
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
        <Link to="/memories" className="inline-flex items-center gap-1 font-mono text-xs text-ink-muted hover:text-ink">
          {t("home-all-memories")} <ArrowRight className="size-3" aria-hidden="true" />
        </Link>
      }
    >
      <ul className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {latest.map((m) => (
          <li key={m.id} className="grid grid-cols-[1rem_1fr] gap-x-2">
            <BookMarked
              className={cn("mt-1 size-4", m.updated_at >= today ? "text-sage" : "text-ink-faint")}
              aria-hidden="true"
            />
            <Link to="/memories" search={m.about ? { about: m.about } : {}} className="group min-w-0">
              <span className="block text-[0.95rem] leading-snug text-pretty text-ink group-hover:text-ember">
                {m.text}
              </span>
              <span className="mt-1 block font-mono text-[0.68rem] text-ink-muted">
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
