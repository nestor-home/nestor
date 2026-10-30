import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { type ReactNode, useState } from "react";
import { type JournalItem, taskQuery, watchQuery } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { dayLabel, hourMinute } from "@/lib/dates";
import { is } from "@/lib/events";
import { kindStyle } from "@/lib/icons";
import { say, why } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { useMe } from "@/lib/session";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";
import { stepLook } from "./steps";
import { type Chain, cast, type Single, type Story, type Thread, type ToolCall, type Turn } from "./stories";

export type Density = "comfortable" | "compact";

interface Props {
  density: Density;
  open: (id: string) => void; // opens the event drawer
  isNew: (id: string) => boolean;
  /** the full thread (its own page): every turn and every detail shown */
  unfolded?: boolean;
}

/** One story of the journal: a conversation thread, a causal chain, or a lone event. */
export function StoryCard({ story, ...props }: Props & { story: Story }) {
  if (story.type === "thread") return <ThreadCard thread={story} {...props} />;
  if (story.type === "chain") return <ChainCard chain={story} {...props} />;
  return <SingleRow single={story} {...props} />;
}

// -- the pieces every story shares -----------------------------------------------------------------

/** A focusable entry: the whole row opens the event drawer; j/k move between entries. */
function Entry({
  item,
  open,
  className,
  children,
  label,
}: {
  item: JournalItem;
  open: (id: string) => void;
  className?: string;
  children: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      data-journal-entry=""
      onClick={() => open(item.id)}
      aria-label={label}
      className={cn(
        "group/entry block w-full min-w-0 rounded-sm py-1 text-left hover:bg-paper-sunken/70 focus-visible:bg-paper-sunken/70",
        className,
      )}
    >
      {children}
    </button>
  );
}

function Clock({ iso, className }: { iso: string; className?: string }) {
  return (
    <time dateTime={iso} className={cn("font-mono text-[0.7rem] text-ink-faint tabular", className)}>
      {hourMinute(iso)}
    </time>
  );
}

function StoryHeader({ story, title, link, kind }: { story: Story; title: ReactNode; link?: ReactNode; kind: string }) {
  const style = kindStyle(kind);
  const Icon = style.icon;
  const name = usePeopleNames();
  const { people, channels, rooms } = cast(story);
  const span =
    story.earliest.slice(0, 16) !== story.latest.slice(0, 16)
      ? `${hourMinute(story.earliest)}–${hourMinute(story.latest)}`
      : hourMinute(story.earliest);
  return (
    <div className="grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-start gap-x-2.5">
      <Icon className={cn("mt-0.5 size-4", style.tone)} aria-hidden="true" />
      <div className="min-w-0">
        <h3 className="font-sans text-[1rem] leading-snug font-medium text-pretty text-ink [overflow-wrap:anywhere]">
          {title}
        </h3>
        {people.length || channels.length || rooms.length ? (
          <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[0.85rem] text-ink-muted">
            {people.map((p) => (
              <span key={p} className="text-ink">
                {name(p)}
              </span>
            ))}
            {channels.map((c) => (
              <span key={c} className="inline-flex items-center gap-1">
                <KindMark kind={c} className="size-3" label={false} />
                {c}
              </span>
            ))}
            {rooms.map((r) => (
              <span key={r}>{r}</span>
            ))}
          </p>
        ) : null}
      </div>
      <p className="flex items-center gap-3 pt-0.5 text-[0.85rem] whitespace-nowrap text-ink-muted tabular">
        {link}
        <span>{span}</span>
      </p>
    </div>
  );
}

const FRAME_LABEL = { thread: "jr-story-thread", chain: "jr-story-chain", single: "jr-story-single" } as const;

function Frame({ children, fresh, story }: { children: ReactNode; fresh: boolean; story: Story }) {
  const t = useT();
  return (
    <article
      aria-label={t(FRAME_LABEL[story.type])}
      className={cn("min-w-0 rounded-lg border border-rule bg-paper-raised px-4 py-4 sm:px-5", fresh && "just-arrived")}
    >
      {children}
    </article>
  );
}

// -- a conversation: a transcript ------------------------------------------------------------------

/** How many turns a long thread shows folded: the first, then the last ones. */
const HEAD = 1;
const TAIL = 2;

function ThreadCard({ thread, density, open, isNew, unfolded }: Props & { thread: Thread }) {
  const t = useT();
  const name = usePeopleNames();
  const [all, setAll] = useState(Boolean(unfolded));
  const { people, channels, rooms } = cast(thread);
  const fresh = thread.items.some((i) => isNew(i.id));
  const turns = thread.turns;
  const hidden = !all && turns.length > HEAD + TAIL + 1 ? turns.length - HEAD - TAIL : 0;
  const shown = hidden ? [...turns.slice(0, HEAD), null, ...turns.slice(-TAIL)] : turns;
  const span =
    thread.earliest.slice(0, 16) !== thread.latest.slice(0, 16)
      ? `${hourMinute(thread.earliest)}–${hourMinute(thread.latest)}`
      : hourMinute(thread.earliest);
  return (
    <Frame fresh={fresh} story={thread}>
      <header className="flex min-w-0 items-baseline gap-3">
        <p className="min-w-0 flex-1 text-[0.92rem] text-ink-muted [overflow-wrap:anywhere]">
          <span className="font-medium text-ink">
            {people.length ? people.map((p) => name(p)).join(", ") : t("jr-story-thread")}
          </span>
          {channels.map((c) => (
            <span key={c}>
              {" · "}
              <KindMark kind={c} className="inline size-3.5 -translate-y-px" label={false} />{" "}
              {c === "voice" ? t("jr-channel-voice") : c}
            </span>
          ))}
          {rooms.map((r) => (
            <span key={r}>{` · ${r}`}</span>
          ))}
          <span className="tabular">{` · ${span} · `}</span>
          {t("jr-turn-count", { count: turns.length })}
        </p>
        {unfolded ? null : (
          <Link
            to="/journal"
            search={{ session: thread.session }}
            className="inline-flex shrink-0 items-center gap-0.5 text-[0.92rem] text-ink-muted hover:text-ink"
            aria-label={t("jr-thread-open")}
          >
            {t("jr-thread-link")} <ArrowUpRight className="size-3.5" aria-hidden="true" />
          </Link>
        )}
      </header>
      {density === "compact" ? (
        <ol className="mt-2 grid gap-0.5">
          {turns.map((turn) => (
            <CompactTurn key={turn.id} turn={turn} open={open} />
          ))}
        </ol>
      ) : (
        <ol className="mt-4 grid gap-5">
          {shown.map((turn, i) =>
            turn ? (
              <TurnBlock key={turn.id} turn={turn} open={open} first={i === 0} unfolded={Boolean(unfolded)} />
            ) : (
              <li key="more">
                <button
                  type="button"
                  onClick={() => setAll(true)}
                  className="w-full rounded-md py-1.5 text-center text-[0.9rem] text-ink-muted hover:bg-paper-sunken hover:text-ink"
                >
                  {t("jr-more-turns", { count: hidden })}
                </button>
              </li>
            ),
          )}
        </ol>
      )}
    </Frame>
  );
}

/** What a turn holds: the reply, what was cut, and everything that happened in between. */
function partsOf(turn: Turn) {
  const events = turn.steps.flatMap((s) => (s.type === "event" ? [s.item] : []));
  const answers = events.filter((i) => is(i, "answer"));
  return {
    answer: answers.at(-1) ?? null,
    cut: events.find((i) => is(i, "cut")) ?? null,
    calls: turn.steps.flatMap((s) => (s.type === "call" ? [s.call] : [])),
    spawns: turn.steps.flatMap((s) => (s.type === "spawn" ? [s.item] : [])),
    others: events.filter((i) => !is(i, "answer") && !is(i, "cut")),
  };
}

const initial = (name: string) => name.slice(0, 1).toUpperCase();

function TurnBlock({
  turn,
  open,
  first,
  unfolded,
}: {
  turn: Turn;
  open: (id: string) => void;
  first: boolean;
  unfolded: boolean;
}) {
  const t = useT();
  const me = useMe();
  const name = usePeopleNames();
  const { answer, cut } = partsOf(turn);
  const who = turn.user ? name(turn.user.people[0]) : "";
  const interrupted = Boolean(cut) || (answer ? is(answer, "interrupted") : false);
  return (
    <li className="grid gap-2.5">
      {turn.user ? (
        <div className="group/msg grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-x-2.5">
          <span
            aria-hidden="true"
            className="mt-0.5 grid size-7 place-items-center rounded-full bg-ink font-serif text-[0.85rem] text-paper"
          >
            {initial(who || "?")}
          </span>
          <div className="min-w-0">
            <p className="mb-1 flex items-baseline gap-2 text-[0.82rem] text-ink-muted">
              <span className="font-medium text-ink">{who}</span>
              <Clock iso={turn.user.at} className={cn(!first && "opacity-0 group-hover/msg:opacity-100")} />
            </p>
            <Entry
              item={turn.user}
              open={open}
              label={t("jr-entry-label", { text: say(turn.user), detail: turn.user.detail })}
              className="w-fit max-w-full rounded-2xl rounded-tl-sm bg-paper-sunken px-3.5 py-2"
            >
              <span className="block text-[0.98rem] leading-relaxed text-ink [overflow-wrap:anywhere]">
                {turn.user.detail || say(turn.user)}
              </span>
            </Entry>
          </div>
        </div>
      ) : (
        <p className="text-[0.85rem] text-ink-faint">{t("jr-thread-earlier")}</p>
      )}
      {answer || cut ? (
        <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-x-2.5">
          <span className="mt-0.5 grid size-7 place-items-center">
            <AgentFigure state="speaking" size="sm" />
          </span>
          <div className="min-w-0">
            <p className="mb-1 text-[0.82rem] font-medium text-ink">{me.assistant}</p>
            {answer ? (
              <Entry
                item={answer}
                open={open}
                label={t("jr-entry-label", { text: say(answer), detail: answer.detail })}
                className="py-0.5"
              >
                <span
                  className={cn(
                    "block text-[0.98rem] leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line",
                    interrupted ? "text-ink-muted" : "text-ink",
                  )}
                >
                  {answer.detail}
                </span>
              </Entry>
            ) : null}
            {cut ? (
              <p className="mt-1 text-[0.88rem] text-ink-muted">{t("jr-cut-by", { heard: cut.detail || "…" })}</p>
            ) : null}
            <Between turn={turn} open={open} unfolded={unfolded} />
          </div>
        </div>
      ) : (
        <div className="pl-[2.375rem]">
          <Between turn={turn} open={open} unfolded={unfolded} />
        </div>
      )}
    </li>
  );
}

/** Everything between a message and its reply, in one quiet line that unfolds into the details. */
function Between({ turn, open, unfolded }: { turn: Turn; open: (id: string) => void; unfolded: boolean }) {
  const t = useT();
  const { calls, spawns, others } = partsOf(turn);
  if (!calls.length && !spawns.length && !others.length) return null;
  const seconds = calls.reduce((n, c) => n + (c.ended?.outcome?.duration_s ?? 0), 0);
  const failed = calls.some((c) => c.ended?.outcome?.ok === false) || others.some((i) => i.tone === "warning");
  const fallback = others.some((i) => is(i, "fallback"));
  const memory = others.some((i) => is(i, "memory"));
  const parts = [
    calls.length ? `${t("jr-tool-count", { count: calls.length })}${seconds ? ` · ${duration(seconds)}` : ""}` : null,
    fallback ? t("jr-fallback") : null,
    memory ? t("jr-memory-kept") : null,
  ].filter(Boolean);
  return (
    <div className="mt-1.5">
      {spawns.map((item) => {
        const isTask = Boolean(item.links.task);
        return (
          <Link
            key={item.id}
            to={isTask ? "/tasks/$taskId" : "/watches/$watchId"}
            params={isTask ? { taskId: item.links.task ?? "" } : { watchId: item.links.watch ?? "" }}
            className="mr-3 inline-flex items-center gap-1 text-[0.85rem] text-ink-muted hover:text-ink"
          >
            <span aria-hidden="true" className="size-1.5 rounded-full bg-kind-task" />
            {say(item)} <ArrowUpRight className="size-3" aria-hidden="true" />
          </Link>
        );
      })}
      {parts.length || calls.length || others.length ? (
        <Collapsible defaultOpen={unfolded}>
          <CollapsibleTrigger
            className="group/between inline-flex items-center gap-1.5 rounded-sm text-[0.85rem] text-ink-muted hover:text-ink"
            aria-label={t("jr-between-details", { what: parts.join(", ") || t("jr-details") })}
          >
            <ChevronRight
              className="size-3 transition-transform group-data-panel-open/between:rotate-90"
              aria-hidden="true"
            />
            {failed || fallback ? (
              <span aria-hidden="true" className={cn("size-1.5 rounded-full", failed ? "bg-brick" : "bg-amber")} />
            ) : null}
            {parts.join(" · ") || t("jr-details")}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 grid gap-2 border-l border-rule pl-3">
              {calls.map((call) => (
                <CallDetail key={call.call} call={call} open={open} />
              ))}
              {others.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    data-journal-entry=""
                    onClick={() => open(item.id)}
                    className="flex min-w-0 items-baseline gap-2 text-left text-[0.88rem] text-ink-muted hover:text-ink"
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 shrink-0 translate-y-[-1px] rounded-full",
                        item.tone === "warning" ? "bg-brick" : kindDot(item.kind),
                      )}
                    />
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      {say(item)}
                      {item.detail ? <span className="text-ink-faint"> · {item.detail}</span> : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}

const kindDot = (kind: string) =>
  kind === "memory"
    ? "bg-sage"
    : kind === "task"
      ? "bg-kind-task"
      : kind === "watch"
        ? "bg-kind-watch"
        : "bg-ink-faint";

function CallDetail({ call, open }: { call: ToolCall; open: (id: string) => void }) {
  const t = useT();
  const ok = call.ended?.outcome?.ok;
  const seconds = call.ended?.outcome?.duration_s;
  const brand = (call.ended ?? call.started)?.brand;
  return (
    <li className="min-w-0">
      <p className="flex flex-wrap items-center gap-x-2 text-[0.88rem]">
        <span
          aria-hidden="true"
          className={cn("size-1.5 rounded-full", ok === undefined ? "bg-amber" : ok ? "bg-sage" : "bg-brick")}
        />
        {brand ? <KindMark kind={brand} className="size-3.5" label={false} /> : null}
        <button
          type="button"
          data-journal-entry=""
          onClick={() => (call.ended ?? call.started) && open((call.ended ?? call.started)?.id ?? "")}
          className="font-mono text-[0.82rem] text-ink [overflow-wrap:anywhere] hover:underline"
          aria-label={t("jr-call-details", { tool: call.name })}
        >
          {call.name}
        </button>
        <span className="text-ink-muted">
          {ok === undefined ? t("jr-call-running") : ok ? t("jr-call-ok") : t("jr-call-failed")}
          {seconds !== undefined && seconds !== null ? ` · ${duration(seconds)}` : ""}
        </span>
      </p>
      {call.started?.detail ? <Code label={t("jr-call-arguments")}>{call.started.detail}</Code> : null}
      {call.ended?.detail ? <Code label={t("jr-call-result")}>{call.ended.detail}</Code> : null}
    </li>
  );
}

/** Arguments or a result: as written, scrolling on its own when it is wider than the page. */
function Code({ label, children }: { label: string; children: string }) {
  return (
    <figure className="mt-1 min-w-0">
      <figcaption className="text-[0.78rem] text-ink-faint">{label}</figcaption>
      <pre className="code-block">{children}</pre>
    </figure>
  );
}

/** Compact: one line per turn, the person then the reply, cut short with the whole on hover. */
function CompactTurn({ turn, open }: { turn: Turn; open: (id: string) => void }) {
  const me = useMe();
  const name = usePeopleNames();
  const { answer } = partsOf(turn);
  const who = turn.user ? name(turn.user.people[0]) : "";
  const line = `${who ? `${who} : ${turn.user?.detail ?? ""}` : ""}${answer ? ` → ${me.assistant} : ${answer.detail}` : ""}`;
  const target = turn.user ?? answer;
  return (
    <li className="min-w-0">
      <button
        type="button"
        data-journal-entry=""
        title={line}
        onClick={() => target && open(target.id)}
        className="flex w-full min-w-0 items-baseline gap-2 rounded-sm px-1 py-0.5 text-left text-[0.92rem] hover:bg-paper-sunken"
      >
        {turn.user ? <Clock iso={turn.user.at} /> : null}
        <span className="min-w-0 truncate">
          {who ? <span className="font-medium text-ink">{who} : </span> : null}
          <span className="text-ink">{turn.user?.detail}</span>
          {answer ? (
            <span className="text-ink-muted">
              {" "}
              → {me.assistant} : {answer.detail}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

// -- a chain ----------------------------------------------------------------------------------------

function useChainTitle(chain: Chain): { title: string; link: ReactNode; kind: string } {
  const t = useT();
  const { type, id } = chain.subject;
  const task = useQuery({ ...taskQuery(id), enabled: type === "task", refetchInterval: false, retry: false });
  const watch = useQuery({ ...watchQuery(id), enabled: type === "watch", retry: false }).data;
  if (type === "task") {
    const objective = task.data?.objective ?? chain.items.find((i) => is(i, "taskStarted"))?.detail;
    return {
      kind: "task",
      title: t("jr-chain-task", { what: objective ?? id }),
      link: (
        <Link to="/tasks/$taskId" params={{ taskId: id }} className="inline-flex items-center gap-0.5 hover:text-ink">
          {t("jr-chain-task-link")} <ArrowUpRight className="size-3" aria-hidden="true" />
        </Link>
      ),
    };
  }
  if (type === "watch") {
    return {
      kind: "watch",
      title: t("jr-chain-watch", { what: watch?.what ?? id }),
      link: (
        <Link
          to="/watches/$watchId"
          params={{ watchId: id }}
          className="inline-flex items-center gap-0.5 hover:text-ink"
        >
          {t("jr-chain-watch-link")} <ArrowUpRight className="size-3" aria-hidden="true" />
        </Link>
      ),
    };
  }
  const first = chain.items[0];
  return { kind: "delivery", title: first ? say(first) : t("jr-chain-delivery"), link: null };
}

function ChainCard({ chain, density, open, isNew }: Props & { chain: Chain }) {
  const { title, link, kind } = useChainTitle(chain);
  const fresh = chain.items.some((i) => isNew(i.id));
  return (
    <Frame fresh={fresh} story={chain}>
      <StoryHeader story={chain} kind={kind} title={title} link={link} />
      {density === "compact" ? (
        <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-[0.85rem]">
          {chain.items.map((item, i) => {
            const look = stepLook(item);
            return (
              <span key={item.id} className="inline-flex items-center gap-1.5">
                {i > 0 ? (
                  <span aria-hidden="true" className="text-ink-faint">
                    →
                  </span>
                ) : null}
                <button
                  type="button"
                  data-journal-entry=""
                  onClick={() => open(item.id)}
                  className={cn("hover:underline", look.tone)}
                >
                  {look.label}
                  {item.room ? ` (${item.room})` : ""}
                </button>
              </span>
            );
          })}
        </p>
      ) : (
        <ol className="relative mt-3">
          {chain.items.map((item, i) => {
            const day = dayLabel(item.at);
            const previous = chain.items[i - 1];
            const newDay = previous ? dayLabel(previous.at) !== day : day !== dayLabel(chain.latest);
            return <ChainStep key={item.id} item={item} open={open} day={newDay ? day : null} />;
          })}
        </ol>
      )}
    </Frame>
  );
}

function ChainStep({
  item,
  open,
  day,
}: {
  item: JournalItem;
  open: (id: string) => void;
  day: string | null; // the day, when the step is on another day than the one before
}) {
  const t = useT();
  const look = stepLook(item);
  const delivered = is(item, "delivered");
  return (
    <li className="grid grid-cols-[2.75rem_0.75rem_minmax(0,1fr)] gap-x-2 pb-2.5 last:pb-0">
      {day ? <span className="col-span-3 pb-1 text-[0.85rem] text-ink-faint first-letter:uppercase">{day}</span> : null}
      <Clock iso={item.at} className="pt-1" />
      <span aria-hidden="true" className={cn("mt-2.5 size-1.5 justify-self-center rounded-full", look.dot)} />
      <Entry item={item} open={open} label={t("jr-entry-label", { text: look.label, detail: say(item) })}>
        <span className="flex flex-wrap items-baseline gap-x-2 text-[0.92rem]">
          <span className="text-ink">{look.label}</span>
          {delivered || is(item, "deliveryFailed") ? (
            <span className="inline-flex flex-wrap items-center gap-x-1.5 text-ink-muted">
              {item.channels.map((c) => (
                <span key={c} className="inline-flex items-center gap-1">
                  <KindMark kind={c} className="size-3" label={false} />
                  {c === "voice" ? t("jr-channel-voice") : c}
                </span>
              ))}
              {item.room ? <span>· {item.room}</span> : null}
            </span>
          ) : null}
        </span>
        {item.reason ? (
          <span className="mt-1 block text-[0.92rem] text-ink [overflow-wrap:anywhere]">
            <span className="text-ink-muted">{t("jr-why")} : </span>
            {why(item)}
          </span>
        ) : null}
        {item.detail ? (
          <span className="mt-0.5 block text-[0.92rem] text-ink-muted [overflow-wrap:anywhere]">{item.detail}</span>
        ) : null}
      </Entry>
    </li>
  );
}

// -- a lone event -----------------------------------------------------------------------------------

function SingleRow({ single, open, isNew }: Props & { single: Single }) {
  const { item } = single;
  const style = kindStyle(item.kind);
  const Icon = style.icon;
  const name = usePeopleNames();
  return (
    <div className={cn("px-4", isNew(item.id) && "just-arrived")}>
      <Entry item={item} open={open} label={say(item)}>
        <span className="grid grid-cols-[2.75rem_1.25rem_minmax(0,1fr)] items-baseline gap-x-2">
          <Clock iso={item.at} />
          <Icon className={cn("size-3.5 translate-y-0.5", style.tone)} aria-hidden="true" />
          <span className="min-w-0 text-[0.92rem] text-ink-muted [overflow-wrap:anywhere]">
            {item.tone === "warning" ? (
              <span aria-hidden="true" className="mr-1.5 inline-block size-1.5 -translate-y-px rounded-full bg-brick" />
            ) : null}
            {say(item)}
            {item.people.length && !say(item).includes(name(item.people[0])) ? (
              <span className="ml-2 text-ink">{item.people.map(name).join(", ")}</span>
            ) : null}
            {item.detail ? <span className="ml-2 text-ink-faint">{item.detail}</span> : null}
          </span>
        </span>
      </Entry>
    </div>
  );
}
