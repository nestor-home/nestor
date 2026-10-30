import { Localized } from "@fluent/react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, House, Send, Volume2 } from "lucide-react";
import {
  type JournalItem,
  journalFacetsQuery,
  journalLatestQuery,
  type Person,
  peopleQuery,
  satellitesQuery,
  tasksQuery,
  watchesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { Dither } from "@/components/dither";
import { Panel, Section } from "@/components/page";
import { Empty, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { Histogram } from "@/features/journal/histogram";
import { useAttention } from "@/features/shell/attention";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, brandOf, KindMark } from "@/lib/brands";
import { startOfToday } from "@/lib/dates";
import { say, why } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";

function greeting(now = new Date()): string {
  const h = now.getHours();
  return tr(h < 5 ? "home-greeting-night" : h < 18 ? "home-greeting-day" : "home-greeting-evening");
}

/** The day in numbers people care about, from today's events. */
function digest(items: JournalItem[]) {
  const sessions = new Set(
    items.filter((i) => i.kind === "conversation" && i.links.session).map((i) => i.links.session),
  );
  return {
    conversations: sessions.size,
    tools: items.filter((i) => i.type.endsWith("tool_completed")).length,
    spoken: items.filter((i) => i.type.endsWith(".delivered")).length,
    memories: items.filter((i) => i.type.endsWith("memory.recorded")).length,
  };
}

export function HomeView() {
  const t = useT();
  const me = useMe();
  const today = startOfToday();
  const latest = useQuery(journalLatestQuery({ from: today }, 200));
  const facets = useQuery(journalFacetsQuery({ from: today }));
  const tasks = useQuery({ ...tasksQuery, enabled: useCan("tasks:read") });
  const { items: attention } = useAttention();
  const navigate = useNavigate();
  const d = digest(latest.data?.items ?? []);
  const running = tasks.data?.running.length ?? 0;

  return (
    <div className="grid gap-10">
      <section
        aria-labelledby="hello"
        className="corner-marks relative overflow-hidden rounded-md border border-rule bg-paper-raised"
      >
        <Dither
          shape="ramp-right"
          from={0}
          to={0.7}
          dot={3}
          className="absolute inset-y-0 right-0 hidden w-1/2 text-ink/15 sm:block"
        />
        <div className="relative grid grid-cols-1 gap-6 p-5 sm:p-7 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] md:p-9">
          <div>
            <h1 id="hello" className="text-[2rem] leading-[1.05] font-normal sm:text-[2.6rem]">
              {t("home-hello", { greeting: greeting(), name: me.account.person_name ?? me.account.login })}
            </h1>
            {latest.data ? (
              <p className="mt-4 max-w-xl text-[1.05rem] leading-relaxed text-pretty text-ink-muted">
                <Localized
                  id="home-summary"
                  vars={{ assistant: me.assistant, conversations: d.conversations, tools: d.tools, spoken: d.spoken }}
                  elems={{ b: <strong className="font-medium text-ink" /> }}
                >
                  <span />
                </Localized>{" "}
                {running ? <>{t("home-running", { count: running })} </> : null}
                {attention.length ? (
                  <span className="text-amber">{t("home-attention", { count: attention.length })}</span>
                ) : (
                  <span className="text-sage">{t("home-all-good")}</span>
                )}
              </p>
            ) : (
              <div className="mt-4 h-14" />
            )}
          </div>
          <div className="self-end rounded-sm bg-paper-raised/85 p-3 backdrop-blur-[1px]">
            <p className="label-mono mb-1">{t("home-activity")}</p>
            <Histogram
              histogram={facets.data?.histogram}
              onRange={(from, to) => void navigate({ to: "/journal", search: { from, to } })}
            />
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <Section title={t("home-attention-title")} count={attention.length}>
            {attention.length === 0 ? (
              <Empty>{t("home-attention-empty")}</Empty>
            ) : (
              <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
                {attention.map((a) => (
                  <li key={a.key} className="flex items-start gap-3 px-4 py-3.5">
                    <a.icon
                      className={cn("mt-0.5 size-4 shrink-0", a.tone === "error" ? "text-brick" : "text-amber")}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-ink">{a.title}</p>
                      {a.detail ? <p className="mt-0.5 text-sm text-ink-muted">{a.detail}</p> : null}
                    </div>
                    <Link
                      {...a.link}
                      className={buttonVariants({ variant: "outline", size: "sm", className: "shrink-0" })}
                    >
                      {a.action}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Deliveries items={latest.data?.items} />
        </div>
        <div className="min-w-0">
          <Home />
          <Now />
        </div>
      </div>
    </div>
  );
}

/** Who is home, where, since when. */
function Home() {
  const t = useT();
  const people = useQuery(peopleQuery);
  if (people.isPending) return <Loading lines={2} />;
  const list = [...(people.data ?? [])].sort((a, b) => rank(a) - rank(b));
  return (
    <Section title={t("home-at-home")} count={list.filter((p) => p.presence?.home).length}>
      <ul className="grid gap-px overflow-hidden rounded-md border border-rule bg-rule">
        {list.map((p) => (
          <li key={p.id} className="bg-paper-raised">
            <Link
              to="/people/$personId"
              params={{ personId: p.id }}
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-paper-sunken/60"
            >
              <House className={cn("size-4", p.presence?.home ? "text-sage" : "text-ink-faint")} aria-hidden="true" />
              <span className="w-20 text-sm text-ink">{p.name}</span>
              <span className="flex-1 truncate font-mono text-xs text-ink-muted">
                {p.presence?.home === true
                  ? (p.presence.room ?? t("home-presence-home"))
                  : p.presence?.home === false
                    ? t("home-presence-away")
                    : t("home-presence-unknown")}
              </span>
              {p.presence?.since ? (
                <Ago iso={p.presence.since} className="font-mono text-[0.7rem] text-ink-faint" />
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function rank(p: Person): number {
  return p.presence?.home === true ? 0 : p.presence?.home === false ? 1 : 2;
}

/** What the agent is doing right now: tasks, watches, devices. */
function Now() {
  const t = useT();
  const canTasks = useCan("tasks:read");
  const canWatches = useCan("watches:read");
  const canSatellites = useCan("satellites:read");
  const tasks = useQuery({ ...tasksQuery, enabled: canTasks });
  const watches = useQuery({ ...watchesQuery, enabled: canWatches });
  const satellites = useQuery({ ...satellitesQuery, enabled: canSatellites });
  return (
    <Section title={t("home-now")}>
      <div className="grid grid-cols-1 gap-5 [&>*]:min-w-0">
        {canTasks ? (
          <div>
            <p className="label-mono mb-1.5">{t("home-now-tasks")}</p>
            {tasks.data?.running.length ? (
              <ul className="grid grid-cols-1 gap-2">
                {tasks.data.running.map((task) => (
                  <li key={task.id} className="min-w-0">
                    <Link to="/tasks/$taskId" params={{ taskId: task.id }} className="group block min-w-0">
                      <span className="flex min-w-0 items-center gap-2 text-sm text-ink group-hover:text-ember">
                        {brandOf(task.executor) ? (
                          <BrandMark brand={brandOf(task.executor) ?? "hermes"} className="size-3.5" />
                        ) : null}
                        <span className="truncate">{task.objective}</span>
                      </span>
                      <span className="mt-0.5 block truncate pl-5.5 font-mono text-[0.7rem] text-ink-muted">
                        {task.steps.at(-1) ?? t("home-task-starting")} · <Ago iso={task.started_at} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-muted">{t("home-no-task")}</p>
            )}
          </div>
        ) : null}
        {canWatches ? (
          <div>
            <p className="label-mono mb-1.5">{t("home-now-watches")}</p>
            <ul className="grid grid-cols-1 gap-1.5">
              {watches.data?.watches.map((w) => (
                <li key={w.id} className="min-w-0">
                  <Link
                    to="/watches/$watchId"
                    params={{ watchId: w.id }}
                    className="block text-sm text-ink hover:text-ember"
                  >
                    <span className="block truncate">{w.what}</span>
                    <span className="font-mono text-[0.7rem] text-ink-muted">
                      {w.last_triggered_at ? (
                        <>
                          {t("home-watch-triggered")} <Ago iso={w.last_triggered_at} />
                        </>
                      ) : (
                        t("home-watch-never")
                      )}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {canSatellites ? (
          <div>
            <p className="label-mono mb-1.5">{t("home-now-satellites")}</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
              {satellites.data?.paired.map((s) => (
                <li key={s.id}>
                  <Link
                    to="/satellites/$satelliteId"
                    params={{ satelliteId: s.id }}
                    className="inline-flex items-center gap-1.5"
                  >
                    <Status tone={s.connected ? "ok" : "idle"}>{s.room}</Status>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Section>
  );
}

/** Every time the agent spoke up today, where and why. */
function Deliveries({ items }: { items: JournalItem[] | undefined }) {
  const t = useT();
  const name = usePeopleNames();
  if (!items) return <Loading lines={3} />;
  const delivered = items.filter((i) => i.type.endsWith(".delivered"));
  // each message's reason is the decision just before it (a follow-up has its own)
  const reasonOf = (d: JournalItem) =>
    why(
      items.find(
        (i) => i.type.endsWith("delivery_considered") && i.links.delivery === d.links.delivery && i.at <= d.at,
      ) ?? {
        reason: null,
      },
    );
  return (
    <Section
      title={t("home-deliveries")}
      count={delivered.length}
      aside={
        <Link
          to="/journal"
          search={{ kinds: "delivery" }}
          className="inline-flex items-center gap-1 font-mono text-xs text-ink-muted hover:text-ink"
        >
          {t("home-all-journal")} <ArrowRight className="size-3" aria-hidden="true" />
        </Link>
      }
    >
      {delivered.length === 0 ? (
        <Empty hint={t("home-deliveries-empty-hint")}>{t("home-deliveries-empty")}</Empty>
      ) : (
        <ol className="grid gap-3">
          {delivered.map((d) => {
            const spoken = d.channels.includes("voice");
            return (
              <li key={d.id}>
                <Panel className="px-4 py-3">
                  <Link to="/journal" search={{ event: d.id }} className="group block">
                    <span className="flex items-center gap-2 font-mono text-[0.7rem] text-ink-muted">
                      {spoken ? (
                        <Volume2 className="size-3.5 text-ember" aria-hidden="true" />
                      ) : (
                        <Send className="size-3.5 text-ember" aria-hidden="true" />
                      )}
                      <span className="text-ember">{d.people.map((p) => name(p)).join(", ")}</span>
                      {d.channels.map((c) => (
                        <span key={c} className="inline-flex items-center gap-1">
                          <KindMark kind={c} className="size-3" label={false} />
                          {spoken ? t("home-delivered-spoken") : t("home-delivered-written", { channel: c })}
                        </span>
                      ))}
                      {d.room ? <span>{d.room}</span> : null}
                      <span className="ml-auto">
                        <Ago iso={d.at} />
                      </span>
                    </span>
                    <span className="mt-1 block text-sm text-ink group-hover:text-ember">{d.detail || say(d)}</span>
                    {reasonOf(d) ? (
                      <span className="mt-1.5 block rounded-sm bg-ember-soft/60 px-2.5 py-1 text-sm text-ink">
                        <span className="font-mono text-[0.7rem] text-ember">{t("jr-why")} </span>
                        {reasonOf(d)}
                      </span>
                    ) : null}
                  </Link>
                </Panel>
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}
