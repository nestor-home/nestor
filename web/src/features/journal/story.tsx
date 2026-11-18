import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { ArrowUpRight, ChevronRight, Megaphone, MessageSquareText, Radar, Workflow } from "lucide-react";
import { type ReactNode, useState } from "react";
import { type JournalItem, taskQuery, watchQuery } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { IconTile, Pebble, type TileTone } from "@/components/marks";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { KindMark, kindName } from "@/lib/brands";
import { dayLabel, hourMinute } from "@/lib/dates";
import { is } from "@/lib/events";
import { say, why } from "@/lib/messages";
import { useMe } from "@/lib/session";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";
import { Attachments } from "./attachments";
import { stepLook } from "./steps";
import { type Chain, cast, type Single, type Story, type Thread, type ToolCall, type Turn } from "./stories";
import { tileOf } from "./tile";

interface Props {
  open: (position: number) => void; // opens the event's sheet
  isNew: (position: number) => boolean;
  /** the full thread (its own page): every turn and every detail shown */
  unfolded?: boolean;
}

/** One story of the journal: a conversation, what a task or a watch went through, or a lone event. */
export function StoryCard({ story, ...props }: Props & { story: Story }) {
  if (story.type === "thread") return <ThreadCard thread={story} {...props} />;
  if (story.type === "chain") return <ChainCard chain={story} {...props} />;
  return <SingleCard single={story} {...props} />;
}

// -- the pieces every story shares -----------------------------------------------------------------

const channelName = (channel: string) => (channel === "voice" ? tr("jr-channel-voice") : kindName(channel));

/** A focusable entry: it opens the event's sheet; j/k move between entries. */
function Entry({
  item,
  open,
  className,
  children,
  label,
}: {
  item: JournalItem;
  open: (position: number) => void;
  className?: string;
  children: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      data-journal-entry=""
      onClick={() => open(item.position)}
      aria-label={label}
      className={cn("block w-full min-w-0 text-left", className)}
    >
      {children}
    </button>
  );
}

function Clock({ iso, className }: { iso: string; className?: string }) {
  return (
    <time dateTime={iso} className={cn("text-[0.85rem] text-ink-muted tabular", className)}>
      {hourMinute(iso)}
    </time>
  );
}

const spanOf = (story: Story) =>
  story.earliest.slice(0, 16) !== story.latest.slice(0, 16)
    ? `${hourMinute(story.earliest)}–${hourMinute(story.latest)}`
    : hourMinute(story.earliest);

/** What leads a story: the tile of its kind, its title, then who is in it, through what, where and when. */
function Head({
  story,
  icon,
  tone,
  title,
  named = true,
  more,
  link,
}: {
  story: Story;
  icon: LucideIcon;
  tone: TileTone;
  title: ReactNode;
  named?: boolean; // the title does not already name the people
  more?: ReactNode;
  link?: ReactNode;
}) {
  const { people, channels, rooms } = cast(story);
  return (
    <header className="flex items-start gap-3.5">
      <IconTile icon={icon} tone={tone} />
      <div className="min-w-0 flex-1">
        <h3 className="font-sans text-[1.02rem] leading-snug font-medium text-pretty text-ink [overflow-wrap:anywhere]">
          {title}
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[0.9rem] text-ink-muted">
          {people.map((p) => (
            <span key={p.id} className="inline-flex items-center gap-1.5 text-ink">
              <Pebble name={p.name} className="size-5 text-[0.6rem]" />
              {named ? p.name : <span className="sr-only">{p.name}</span>}
            </span>
          ))}
          {channels.map((c) => (
            <span key={c} className="inline-flex items-center gap-1">
              <KindMark kind={c} className="size-3.5" label={false} />
              {channelName(c)}
            </span>
          ))}
          {rooms.map((r) => (
            <span key={r}>{r}</span>
          ))}
          <span className="tabular">{spanOf(story)}</span>
          {more}
        </p>
      </div>
      {link}
    </header>
  );
}

const LINK = "inline-flex shrink-0 items-center gap-0.5 pt-0.5 text-[0.9rem] text-ink-muted hover:text-ink";
const FRAME_LABEL = { thread: "jr-story-thread", chain: "jr-story-chain", single: "jr-story-single" } as const;

function Frame({ children, fresh, story }: { children: ReactNode; fresh: boolean; story: Story }) {
  const t = useT();
  return (
    <article
      aria-label={t(FRAME_LABEL[story.type])}
      className={cn("surface min-w-0", story.type === "single" ? "p-3.5" : "p-4 sm:p-5", fresh && "just-arrived")}
    >
      {children}
    </article>
  );
}

// -- a conversation: what was said, the person's words and the agent's set apart ------------------------

/** How many turns a long thread shows folded: the first, then the last ones. */
const HEAD = 1;
const TAIL = 2;

function ThreadCard({ thread, open, isNew, unfolded }: Props & { thread: Thread }) {
  const t = useT();
  const [all, setAll] = useState(Boolean(unfolded));
  const { people } = cast(thread);
  const turns = thread.turns;
  const hidden = !all && turns.length > HEAD + TAIL + 1 ? turns.length - HEAD - TAIL : 0;
  const shown = hidden ? [...turns.slice(0, HEAD), null, ...turns.slice(-TAIL)] : turns;
  return (
    <Frame fresh={thread.items.some((i) => isNew(i.position))} story={thread}>
      <Head
        story={thread}
        icon={MessageSquareText}
        tone="ink"
        named={false}
        title={people.length ? people.map((p) => p.name).join(", ") : t("jr-story-thread")}
        more={<span>{t("jr-turn-count", { count: turns.length })}</span>}
        link={
          unfolded ? null : (
            <Link to="/journal" search={thread.filter} className={LINK} aria-label={t("jr-thread-open")}>
              {t("jr-thread-link")} <ArrowUpRight className="size-3.5" aria-hidden="true" />
            </Link>
          )
        }
      />
      <ol className="mt-4 grid gap-4">
        {shown.map((turn) =>
          turn ? (
            <TurnBlock key={turn.id} turn={turn} open={open} unfolded={Boolean(unfolded)} />
          ) : (
            <li key="more">
              <button
                type="button"
                onClick={() => setAll(true)}
                className="w-full rounded-full bg-paper-sunken py-1.5 text-center text-[0.9rem] text-ink-muted hover:text-ink"
              >
                {t("jr-more-turns", { count: hidden })}
              </button>
            </li>
          ),
        )}
      </ol>
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

const SIDE = "grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-x-2.5";

function TurnBlock({ turn, open, unfolded }: { turn: Turn; open: (position: number) => void; unfolded: boolean }) {
  const t = useT();
  const me = useMe();
  const { answer, cut } = partsOf(turn);
  const who = turn.user?.people[0]?.name ?? (turn.user ? tr("household-everyone") : "");
  const interrupted = Boolean(cut) || (answer ? is(answer, "interrupted") : false);
  return (
    <li className="grid gap-3">
      {turn.user ? (
        <div className={SIDE}>
          <Pebble name={who || "?"} className="mt-5" />
          <div className="min-w-0">
            <p className="mb-1 flex items-baseline gap-2 text-[0.85rem] text-ink-muted">
              <span className="font-medium text-ink">{who}</span>
              <Clock iso={turn.user.at} />
            </p>
            <Entry
              item={turn.user}
              open={open}
              label={t("jr-entry-label", { text: say(turn.user), detail: turn.user.detail_text })}
              className="w-fit max-w-full rounded-2xl rounded-tl-sm bg-paper-sunken px-3.5 py-2 hover:bg-rule"
            >
              <span className="block text-[0.98rem] leading-relaxed text-ink [overflow-wrap:anywhere]">
                {turn.user.detail_text || say(turn.user)}
              </span>
            </Entry>
            <Attachments item={turn.user} className="mt-2" />
          </div>
        </div>
      ) : (
        <p className="text-[0.9rem] text-ink-muted">{t("jr-thread-earlier")}</p>
      )}
      {answer || cut ? (
        <div className={SIDE}>
          <span className="mt-5 grid size-7 place-items-center">
            <AgentFigure state="speaking" size="sm" />
          </span>
          <div className="min-w-0">
            <p className="mb-0.5 text-[0.85rem] font-medium text-ember">{me.assistant}</p>
            {answer ? (
              <Entry
                item={answer}
                open={open}
                label={t("jr-entry-label", { text: say(answer), detail: answer.detail_text })}
                className="-mx-2 -my-1 rounded-lg px-2 py-1 hover:bg-paper-sunken/70"
              >
                <span
                  className={cn(
                    "block font-serif text-[1.1rem] leading-snug [overflow-wrap:anywhere] whitespace-pre-line",
                    interrupted ? "text-ink-muted" : "text-ink",
                  )}
                >
                  {answer.detail_text}
                </span>
              </Entry>
            ) : null}
            {cut ? (
              <p className="mt-1 text-[0.9rem] text-ink-muted">{t("jr-cut-by", { heard: cut.detail_text || "…" })}</p>
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
function Between({ turn, open, unfolded }: { turn: Turn; open: (position: number) => void; unfolded: boolean }) {
  const t = useT();
  const { calls, spawns, others } = partsOf(turn);
  if (!calls.length && !spawns.length && !others.length) return null;
  const seconds = calls.reduce((n, c) => n + (c.ended?.outcome?.duration_s ?? 0), 0);
  const failed = calls.some((c) => c.ended?.outcome?.ok === false) || others.some((i) => i.tone === "warning");
  const fallback = others.some((i) => is(i, "fallback"));
  const memory = others.some((i) => is(i, "memory"));
  const files = [...calls.map((c) => c.ended), ...others].reduce((n, i) => n + (i?.attachments.length ?? 0), 0);
  const parts = [
    calls.length ? `${t("jr-tool-count", { count: calls.length })}${seconds ? ` · ${duration(seconds)}` : ""}` : null,
    files ? t("jr-file-count", { count: files }) : null,
    fallback ? t("jr-fallback") : null,
    memory ? t("jr-memory-kept") : null,
  ].filter(Boolean);
  return (
    <div className="mt-2 grid justify-items-start gap-1.5">
      {spawns.map((item) => {
        const isTask = Boolean(item.links.task);
        return (
          <Link
            key={item.id}
            to={isTask ? "/tasks/$taskId" : "/watches/$watchId"}
            params={isTask ? { taskId: item.links.task ?? "" } : { watchId: item.links.watch ?? "" }}
            className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-paper-sunken px-3 py-1 text-[0.9rem] text-ink hover:bg-rule"
          >
            {isTask ? (
              <Workflow className="size-3.5 shrink-0 text-kind-task" aria-hidden="true" />
            ) : (
              <Radar className="size-3.5 shrink-0 text-kind-watch" aria-hidden="true" />
            )}
            <span className="truncate">{say(item)}</span>
            <ArrowUpRight className="size-3 shrink-0 text-ink-faint" aria-hidden="true" />
          </Link>
        );
      })}
      {calls.length || others.length ? (
        <Collapsible defaultOpen={unfolded} className="w-full min-w-0">
          <CollapsibleTrigger
            className="group/between inline-flex items-center gap-1.5 rounded-sm text-[0.9rem] text-ink-muted hover:text-ink"
            aria-label={t("jr-between-details", { what: parts.join(", ") || t("jr-details") })}
          >
            <ChevronRight
              className="size-3.5 transition-transform group-data-panel-open/between:rotate-90"
              aria-hidden="true"
            />
            {failed || fallback ? (
              <span aria-hidden="true" className={cn("size-1.5 rounded-full", failed ? "bg-brick" : "bg-amber")} />
            ) : null}
            {parts.join(" · ") || t("jr-details")}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 grid gap-3 rounded-xl bg-paper-sunken/60 p-3">
              {calls.map((call) => (
                <CallDetail key={call.call} call={call} open={open} />
              ))}
              {others.map((item) => (
                <li key={item.id} className="min-w-0">
                  <button
                    type="button"
                    data-journal-entry=""
                    onClick={() => open(item.position)}
                    className="flex min-w-0 items-baseline gap-2 text-left text-[0.9rem] text-ink-muted hover:text-ink"
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 shrink-0 -translate-y-px rounded-full",
                        item.tone === "warning" ? "bg-brick" : kindDot(item.kind),
                      )}
                    />
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      {say(item)}
                      {item.detail_text ? <span className="text-ink-faint"> · {item.detail_text}</span> : null}
                    </span>
                  </button>
                  <Attachments item={item} className="mt-1.5 pl-3.5" />
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

function CallDetail({ call, open }: { call: ToolCall; open: (position: number) => void }) {
  const t = useT();
  const ok = call.ended?.outcome?.ok;
  const seconds = call.ended?.outcome?.duration_s;
  const brand = call.started?.brand ?? call.ended?.brand;
  const event = call.ended ?? call.started;
  return (
    <li className="min-w-0">
      <p className="flex flex-wrap items-center gap-x-2 text-[0.9rem]">
        <span
          aria-hidden="true"
          className={cn("size-1.5 rounded-full", ok === undefined ? "bg-amber" : ok ? "bg-sage" : "bg-brick")}
        />
        {brand ? <KindMark kind={brand} className="size-3.5" label={false} /> : null}
        <button
          type="button"
          data-journal-entry=""
          onClick={() => event && open(event.position)}
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
      {call.started?.detail_text ? <Code label={t("jr-call-arguments")}>{call.started.detail_text}</Code> : null}
      {call.ended?.detail_text ? <Code label={t("jr-call-result")}>{call.ended.detail_text}</Code> : null}
      {call.ended ? <Attachments item={call.ended} className="mt-1.5" /> : null}
    </li>
  );
}

/** Arguments or a result: as written, scrolling on its own when it is wider than the page. */
function Code({ label, children }: { label: string; children: string }) {
  return (
    <figure className="mt-1 min-w-0">
      <figcaption className="text-[0.82rem] text-ink-muted">{label}</figcaption>
      <pre className="code-block">{children}</pre>
    </figure>
  );
}

// -- what a task, a watch or a message of its own went through ------------------------------------------

function useChainHead(chain: Chain): { title: string; link: ReactNode; icon: LucideIcon; tone: TileTone } {
  const t = useT();
  const { type, id } = chain.subject;
  const task = useQuery({ ...taskQuery(id), enabled: type === "task", refetchInterval: false, retry: false });
  const watch = useQuery({ ...watchQuery(id), enabled: type === "watch", retry: false }).data;
  if (type === "task") {
    const name = task.data?.title ?? chain.items.find((i) => is(i, "taskStarted"))?.detail;
    return {
      icon: Workflow,
      tone: "task",
      title: t("jr-chain-task", { what: name ?? id }),
      link: (
        <Link to="/tasks/$taskId" params={{ taskId: id }} className={LINK}>
          {t("jr-chain-task-link")} <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </Link>
      ),
    };
  }
  if (type === "watch") {
    return {
      icon: Radar,
      tone: "watch",
      title: t("jr-chain-watch", { what: watch?.title ?? id }),
      link: (
        <Link to="/watches/$watchId" params={{ watchId: id }} className={LINK}>
          {t("jr-chain-watch-link")} <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </Link>
      ),
    };
  }
  const first = chain.items[0];
  return { icon: Megaphone, tone: "ember", title: first ? say(first) : t("jr-chain-delivery"), link: null };
}

function ChainCard({ chain, open, isNew }: Props & { chain: Chain }) {
  const head = useChainHead(chain);
  return (
    <Frame fresh={chain.items.some((i) => isNew(i.position))} story={chain}>
      <Head story={chain} {...head} />
      <ol className="mt-4 grid gap-2.5">
        {chain.items.map((item, i) => {
          const day = dayLabel(item.at);
          const previous = chain.items[i - 1];
          const newDay = previous ? dayLabel(previous.at) !== day : day !== dayLabel(chain.latest);
          return <ChainStep key={item.id} item={item} open={open} day={newDay ? day : null} />;
        })}
      </ol>
    </Frame>
  );
}

function ChainStep({
  item,
  open,
  day,
}: {
  item: JournalItem;
  open: (position: number) => void;
  day: string | null; // the day, when the step is on another day than the one before
}) {
  const t = useT();
  const look = stepLook(item);
  const Icon = look.icon;
  return (
    <li className="grid grid-cols-[2.75rem_1.25rem_minmax(0,1fr)] items-baseline gap-x-2">
      {day ? <span className="col-span-3 pb-1 text-[0.85rem] text-ink-muted first-letter:uppercase">{day}</span> : null}
      <Clock iso={item.at} />
      <Icon className={cn("size-3.5 translate-y-0.5 justify-self-center", look.tone)} aria-hidden="true" />
      <div className="min-w-0">
        <Entry
          item={item}
          open={open}
          label={t("jr-entry-label", { text: look.label, detail: say(item) })}
          className="-mx-2 -my-1 rounded-lg px-2 py-1 hover:bg-paper-sunken/70"
        >
          <span className="flex flex-wrap items-baseline gap-x-2 text-[0.95rem]">
            <span className="font-medium text-ink">{look.label}</span>
            <Source item={item} />
            {is(item, "delivered") || is(item, "deliveryFailed") ? (
              <span className="inline-flex flex-wrap items-center gap-x-1.5 text-ink-muted">
                {item.channels.map((c) => (
                  <span key={c} className="inline-flex items-center gap-1">
                    <KindMark kind={c} className="size-3.5" label={false} />
                    {channelName(c)}
                  </span>
                ))}
                {item.room ? <span>· {item.room}</span> : null}
              </span>
            ) : null}
          </span>
          {item.reason ? (
            <span className="mt-0.5 block text-[0.95rem] text-ink [overflow-wrap:anywhere]">
              <span className="text-ember">{t("jr-why-label")} </span>
              {why(item)}
            </span>
          ) : null}
          {item.detail_text ? (
            <span className="mt-0.5 block text-[0.95rem] text-ink-muted [overflow-wrap:anywhere]">
              {item.detail_text}
            </span>
          ) : null}
        </Entry>
        <Attachments item={item} className="mt-1.5" />
      </div>
    </li>
  );
}

const sourced = (item: JournalItem): item is JournalItem & { brand: string } =>
  Boolean(item.brand) && (is(item, "watchTriggered") || is(item, "watchSorted"));

/** What brought an item a watch looked at: the account it came to, the feed, the page or the webhook. */
function Source({ item }: { item: JournalItem }) {
  if (!sourced(item)) return null;
  return (
    <span className="inline-flex items-center gap-1 text-ink-muted">
      <KindMark kind={item.brand} className="size-3.5" label={false} />
      {kindName(item.brand)}
    </span>
  );
}

// -- a lone event -----------------------------------------------------------------------------------

function SingleCard({ single, open, isNew }: Props & { single: Single }) {
  const { item } = single;
  const text = say(item);
  const people = item.people.filter((p) => !text.includes(p.name));
  return (
    <Frame fresh={isNew(item.position)} story={single}>
      <Entry item={item} open={open} label={text} className="-m-1.5 w-auto rounded-xl p-1.5 hover:bg-paper-sunken/60">
        <span className="flex items-center gap-3.5">
          <IconTile {...tileOf(item)} className="size-9" />
          <span className="min-w-0 flex-1">
            <span className="block text-[0.98rem] text-ink [overflow-wrap:anywhere]">{text}</span>
            {people.length || item.detail_text || sourced(item) ? (
              <span className="flex flex-wrap items-center gap-x-2.5 text-[0.88rem] text-ink-muted">
                <Source item={item} />
                {people.map((p) => (
                  <span key={p.id} className="inline-flex items-center gap-1.5">
                    <Pebble name={p.name} className="size-4.5 text-[0.55rem]" />
                    {p.name}
                  </span>
                ))}
                {item.detail_text ? <span className="line-clamp-2 min-w-0">{item.detail_text}</span> : null}
              </span>
            ) : null}
          </span>
          <Clock iso={item.at} />
        </span>
      </Entry>
      <Attachments item={item} className="mt-3 pl-[3.125rem]" />
    </Frame>
  );
}
