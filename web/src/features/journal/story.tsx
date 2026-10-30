import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, ChevronRight, Scissors } from "lucide-react";
import type { ReactNode } from "react";
import { type JournalItem, tasksQuery, watchesQuery } from "@/api";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { dayLabel, hourMinute } from "@/lib/dates";
import { kindStyle } from "@/lib/icons";
import { say, why } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { useMe } from "@/lib/session";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";
import { stepLook } from "./steps";
import { type Chain, cast, type Single, type Step, type Story, type Thread, type ToolCall, type Turn } from "./stories";

export type Density = "comfortable" | "compact";

interface Props {
  density: Density;
  open: (id: string) => void; // opens the event drawer
  isNew: (id: string) => boolean;
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
        "group/entry -mx-2 block w-[calc(100%+1rem)] rounded-sm px-2 py-1 text-left hover:bg-paper-sunken/70 focus-visible:bg-paper-sunken/70",
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
        <h3 className="line-clamp-2 text-[1.02rem] leading-snug font-normal text-pretty text-ink">{title}</h3>
        {people.length || channels.length || rooms.length ? (
          <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 font-mono text-[0.7rem] text-ink-muted">
            {people.map((p) => (
              <span key={p} className="text-ember">
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
      <p className="flex items-center gap-3 pt-0.5 font-mono text-[0.7rem] whitespace-nowrap text-ink-faint tabular">
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
      className={cn("rounded-md border border-rule bg-paper-raised px-4 py-3", fresh && "just-arrived")}
    >
      {children}
    </article>
  );
}

// -- a conversation ---------------------------------------------------------------------------------

function ThreadCard({ thread, density, open, isNew }: Props & { thread: Thread }) {
  const t = useT();
  const name = usePeopleNames();
  const { people } = cast(thread);
  const fresh = thread.items.some((i) => isNew(i.id));
  const title = t("jr-thread-title", { people: people.map((p) => name(p)).join(", "), count: people.length });
  return (
    <Frame fresh={fresh} story={thread}>
      <StoryHeader
        story={thread}
        kind="conversation"
        title={title}
        link={
          <Link
            to="/journal"
            search={{ session: thread.session }}
            className="inline-flex items-center gap-0.5 hover:text-ink"
            aria-label={t("jr-thread-open")}
          >
            {t("jr-thread-link")} <ArrowUpRight className="size-3" aria-hidden="true" />
          </Link>
        }
      />
      <ol className={cn("mt-2", density === "compact" ? "space-y-0" : "space-y-2")}>
        {thread.turns.map((turn) => (
          <TurnBlock key={turn.id} turn={turn} density={density} open={open} />
        ))}
      </ol>
    </Frame>
  );
}

function TurnBlock({ turn, density, open }: { turn: Turn; density: Density; open: (id: string) => void }) {
  const t = useT();
  const name = usePeopleNames();
  const calls = turn.steps.filter((s) => s.type === "call").length;
  return (
    <li>
      {turn.user ? (
        <Entry
          item={turn.user}
          open={open}
          label={t("jr-entry-label", { text: say(turn.user), detail: turn.user.detail })}
        >
          <span className="grid grid-cols-[2.75rem_1fr] gap-x-2">
            <Clock iso={turn.user.at} className="pt-0.5" />
            <span className={cn("text-ink", density === "compact" && "truncate")}>
              <span className="mr-2 font-medium">{name(turn.user.people[0])}</span>
              <q className="font-serif text-[1.02rem] [font-variation-settings:'opsz'_16]">{turn.user.detail}</q>
              {density === "compact" && calls ? (
                <span className="ml-2 font-mono text-[0.7rem] text-ink-faint">
                  {t("jr-tool-count", { count: calls })}
                </span>
              ) : null}
            </span>
          </span>
        </Entry>
      ) : (
        <p className="pl-[3.25rem] font-mono text-[0.7rem] text-ink-faint">{t("jr-thread-earlier")}</p>
      )}
      <ol className="ml-[3.25rem]">
        {turn.steps
          .filter((s) => density === "comfortable" || !(s.type === "call"))
          .map((step, i, all) => (
            <StepRow key={stepKey(step)} step={step} last={i === all.length - 1} density={density} open={open} />
          ))}
      </ol>
    </li>
  );
}

function stepKey(step: Step): string {
  return step.type === "call" ? `call-${step.call.call}` : `${step.type}-${step.item.id}`;
}

/** A tree branch drawn in mono, like `tree`: structure without coloured strips. */
function Branch({ last }: { last: boolean }) {
  return (
    <span aria-hidden="true" className="w-4 shrink-0 font-mono text-[0.75rem] leading-6 text-ink-faint select-none">
      {last ? "└" : "├"}
    </span>
  );
}

function StepRow({
  step,
  last,
  density,
  open,
}: {
  step: Step;
  last: boolean;
  density: Density;
  open: (id: string) => void;
}) {
  const t = useT();
  const me = useMe();
  if (step.type === "call") return <CallRow call={step.call} last={last} open={open} />;
  const item = step.item;
  if (step.type === "spawn") {
    const isTask = Boolean(item.links.task);
    return (
      <li className="flex items-start">
        <Branch last={last} />
        <Link
          to={isTask ? "/tasks/$taskId" : "/watches/$watchId"}
          params={isTask ? { taskId: item.links.task ?? "" } : { watchId: item.links.watch ?? "" }}
          className="inline-flex items-center gap-1.5 py-0.5 text-sm text-kind-task hover:underline"
        >
          {(() => {
            const Icon = kindStyle(item.kind).icon;
            return <Icon className="size-3.5" aria-hidden="true" />;
          })()}
          {say(item)}
          <ArrowUpRight className="size-3" aria-hidden="true" />
        </Link>
      </li>
    );
  }
  const answer = item.type.endsWith("assistant_turn");
  const cut = item.type.endsWith("answer_cut");
  const interrupted = item.message.id === "journal-assistant-interrupted";
  return (
    <li className="flex items-start">
      <Branch last={last} />
      <Entry
        item={item}
        open={open}
        label={t("jr-entry-label", { text: say(item), detail: item.detail })}
        className="py-0.5"
      >
        <span className={cn("block text-sm", density === "compact" && "truncate")}>
          {answer ? (
            <>
              <span className="mr-2 font-medium text-ink">{me.assistant}</span>
              <span className={cn("text-ink", interrupted && "text-ink-muted")}>{item.detail}</span>
              {interrupted ? (
                <span className="ml-2 font-mono text-[0.7rem] text-amber">{t("jr-interrupted")}</span>
              ) : null}
            </>
          ) : cut ? (
            <span className="inline-flex items-center gap-1.5 text-amber">
              <Scissors className="size-3.5" aria-hidden="true" />
              {item.detail}
            </span>
          ) : (
            <span
              className={cn(
                "inline-flex items-center gap-1.5",
                item.tone === "warning" ? "text-brick" : "text-ink-muted",
              )}
            >
              {(() => {
                const Icon = kindStyle(item.kind).icon;
                return <Icon className={cn("size-3.5", kindStyle(item.kind).tone)} aria-hidden="true" />;
              })()}
              {say(item)}
              {item.detail ? <span className="text-ink-muted">— {item.detail}</span> : null}
            </span>
          )}
        </span>
      </Entry>
    </li>
  );
}

function CallRow({ call, last, open }: { call: ToolCall; last: boolean; open: (id: string) => void }) {
  const t = useT();
  const ok = call.ended?.outcome?.ok;
  const seconds = call.ended?.outcome?.duration_s;
  const brand = (call.ended ?? call.started)?.brand;
  return (
    <li className="flex items-start">
      <Branch last={last} />
      <Collapsible className="min-w-0 flex-1">
        <div className="flex items-center gap-2 py-0.5">
          <CollapsibleTrigger
            className="group/call inline-flex items-center gap-1.5 rounded-sm font-mono text-[0.78rem] text-ink hover:text-ember"
            aria-label={t("jr-call-details", { tool: call.name })}
          >
            <ChevronRight
              className="size-3 text-ink-faint transition-transform group-data-panel-open/call:rotate-90"
              aria-hidden="true"
            />
            {brand ? <KindMark kind={brand} className="size-3.5" label={false} /> : null}
            {call.name}
          </CollapsibleTrigger>
          {seconds !== undefined && seconds !== null ? (
            <span className="font-mono text-[0.68rem] text-ink-faint tabular">{duration(seconds)}</span>
          ) : null}
          {ok === undefined ? (
            <span className="font-mono text-[0.68rem] text-amber">{t("jr-call-running")}</span>
          ) : ok ? (
            <span className="font-mono text-[0.68rem] text-sage">{t("jr-call-ok")}</span>
          ) : (
            <span className="font-mono text-[0.68rem] text-brick">{t("jr-call-failed")}</span>
          )}
        </div>
        <CollapsibleContent className="mb-1 grid gap-1 rounded-sm bg-paper-sunken px-3 py-2 font-mono text-[0.72rem] text-ink-muted">
          {call.started ? (
            <button
              type="button"
              className="text-left hover:text-ink"
              onClick={() => call.started && open(call.started.id)}
            >
              <span className="text-ink-faint">{t("jr-call-arguments")} </span>
              {call.started.detail}
            </button>
          ) : null}
          {call.ended ? (
            <button
              type="button"
              className={cn("text-left hover:text-ink", ok === false && "text-brick")}
              onClick={() => call.ended && open(call.ended.id)}
            >
              <span className="text-ink-faint">{t("jr-call-result")} </span>
              {call.ended.detail}
            </button>
          ) : null}
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

// -- a chain ----------------------------------------------------------------------------------------

function useChainTitle(chain: Chain): { title: string; link: ReactNode; kind: string } {
  const t = useT();
  const tasks = useQuery({ ...tasksQuery, refetchInterval: false });
  const watches = useQuery({ ...watchesQuery });
  const { type, id } = chain.subject;
  if (type === "task") {
    const task = [...(tasks.data?.running ?? []), ...(tasks.data?.recent ?? [])].find((t) => t.id === id);
    const objective = task?.objective ?? chain.items.find((i) => i.type.endsWith("task_started"))?.detail;
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
    const watch = watches.data?.watches.find((w) => w.id === id);
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
        <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 font-mono text-[0.72rem]">
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
            return (
              <ChainStep
                key={item.id}
                item={item}
                last={i === chain.items.length - 1}
                open={open}
                day={newDay ? day : null}
              />
            );
          })}
        </ol>
      )}
    </Frame>
  );
}

function ChainStep({
  item,
  last,
  open,
  day,
}: {
  item: JournalItem;
  last: boolean;
  open: (id: string) => void;
  day: string | null; // the day, when the step is on another day than the one before
}) {
  const t = useT();
  const look = stepLook(item);
  const Icon = look.icon;
  const delivered = item.type.endsWith(".delivered");
  return (
    <li className="relative grid grid-cols-[2.75rem_1.5rem_1fr] gap-x-2 pb-2 last:pb-0">
      {day ? (
        <span className="col-span-3 pb-1 font-mono text-[0.66rem] text-ink-faint first-letter:uppercase">{day}</span>
      ) : null}
      <Clock iso={item.at} className="pt-1.5" />
      <span className="relative flex justify-center">
        {last ? null : <span aria-hidden="true" className="absolute top-6 -bottom-2 w-px bg-rule-strong" />}
        <span className="relative mt-1 grid size-5 place-items-center rounded-full border border-rule-strong bg-paper-raised">
          <Icon className={cn("size-3", look.tone)} aria-hidden="true" />
        </span>
      </span>
      <Entry item={item} open={open} label={t("jr-entry-label", { text: look.label, detail: say(item) })}>
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className={cn("font-mono text-[0.72rem]", look.tone)}>{look.label}</span>
          {delivered || item.type.endsWith("delivery_failed") ? (
            <span className="inline-flex items-center gap-1 font-mono text-[0.7rem] text-ink-muted">
              {item.channels.map((c) => (
                <span key={c} className="inline-flex items-center gap-1">
                  <KindMark kind={c} className="size-3" label={false} />
                  {c === "voice" ? t("jr-channel-voice") : c}
                </span>
              ))}
              {item.room ? <span>{item.room}</span> : null}
            </span>
          ) : null}
        </span>
        {item.reason ? (
          <span className="mt-1 block rounded-sm bg-ember-soft/70 px-2.5 py-1.5 text-sm text-ink">
            <span className="font-mono text-[0.7rem] text-ember">{t("jr-why")} </span>
            {why(item)}
          </span>
        ) : null}
        {item.detail ? (
          <span className={cn("mt-0.5 block text-sm", item.tone === "warning" ? "text-brick" : "text-ink-muted")}>
            {item.detail}
          </span>
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
        <span className="grid grid-cols-[2.75rem_1.25rem_1fr] items-baseline gap-x-2">
          <Clock iso={item.at} />
          <Icon className={cn("size-3.5 translate-y-0.5", style.tone)} aria-hidden="true" />
          <span className={cn("truncate text-sm", item.tone === "warning" ? "text-brick" : "text-ink-muted")}>
            {say(item)}
            {item.people.length && !say(item).includes(name(item.people[0])) ? (
              <span className="ml-2 font-mono text-[0.7rem] text-ember">{item.people.map(name).join(", ")}</span>
            ) : null}
            {item.detail ? <span className="ml-2 text-ink-faint">{item.detail}</span> : null}
          </span>
        </span>
      </Entry>
    </div>
  );
}
