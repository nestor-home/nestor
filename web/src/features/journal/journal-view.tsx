/**
 * The journal: everything that happened, as stories (a conversation and its tool calls, a watch that fired and
 * what followed, a task's run), newest first, day by day. Its lanes, search and filters live in the URL; an event
 * opens in its sheet with the raw record. `/` searches, `j` and `k` move between entries, `p` pauses the live edge.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { type JournalFacets, journalFacetsQuery, type Kind } from "@/api";
import { Chips } from "@/components/chips";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useLive } from "@/features/shell/live";
import { useIsMobile } from "@/hooks/use-mobile";
import { useT } from "@/i18n";
import { dayLabel } from "@/lib/dates";
import { EventSheet } from "./event-sheet";
import { FilterBar, FilterSheet } from "./facets";
import { Histogram } from "./histogram";
import { clean, filtersOf, type JournalSearch } from "./search";
import type { Story } from "./stories";
import { StoryCard } from "./story";
import { PeriodPicker, SearchField } from "./toolbar";
import { useJournal } from "./use-journal";

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** The lanes most read, each a set of kinds; "problems" is what went wrong, whatever its kind. */
const LANES = {
  talk: ["conversation", "tool"],
  own: ["delivery", "schedule"],
  tasks: ["task"],
  watches: ["watch"],
  memory: ["memory"],
} as const satisfies Record<string, readonly Kind[]>;

type Lane = "all" | keyof typeof LANES | "problems" | "custom";

const LANE_IDS = ["all", "talk", "own", "tasks", "watches", "memory", "problems"] as const satisfies readonly Lane[];

function laneOf({ kinds, tone }: JournalSearch): Lane {
  if (!kinds?.length) return tone === "warning" ? "problems" : tone ? "custom" : "all";
  if (tone) return "custom";
  for (const [lane, of] of Object.entries(LANES) as [keyof typeof LANES, readonly Kind[]][]) {
    if (of.length === kinds.length && of.every((k) => kinds.includes(k))) return lane;
  }
  return "custom"; // kinds picked one by one in the filters
}

function inLane(search: JournalSearch, lane: Lane): JournalSearch {
  if (lane === "problems") return { ...search, kinds: undefined, tone: "warning" };
  return { ...search, tone: undefined, kinds: lane === "all" || lane === "custom" ? undefined : [...LANES[lane]] };
}

export function JournalView({ search, onSearch }: { search: JournalSearch; onSearch: (next: JournalSearch) => void }) {
  const t = useT();
  const mobile = useIsMobile();
  const [following, setFollowing] = useState(true);
  const searchInput = useRef<HTMLInputElement>(null);
  const filters = filtersOf(search);
  const facets = useQuery(journalFacetsQuery(filters));
  const set = (next: JournalSearch) => onSearch(clean(next));
  const trail: Crumb[] = [{ label: t("space-today"), link: { to: "/" } }, { label: t("jr-title") }];

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (TYPING.has(target.tagName) || target.isContentEditable || target.closest("[role=dialog]")) return;
      if (event.key === "/") {
        event.preventDefault();
        searchInput.current?.focus();
      } else if (event.key === "p") {
        setFollowing((f) => !f);
      } else if (event.key === "j" || event.key === "k") {
        const entries = [...document.querySelectorAll<HTMLElement>("[data-journal-entry]")];
        if (!entries.length) return;
        event.preventDefault();
        const at = entries.indexOf(document.activeElement as HTMLElement);
        const next = event.key === "j" ? Math.min(entries.length - 1, at + 1) : Math.max(0, at - 1);
        entries[at === -1 ? 0 : next]?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="grid gap-10">
      <div className="min-w-0">
        <PageHeader
          title={t("jr-title")}
          crumbs={<Crumbs trail={trail} />}
          meta={<Edge following={following} live={!search.to} facets={facets.data} />}
          actions={
            search.to ? null : (
              <Button
                variant={following ? "outline" : "accent"}
                onClick={() => setFollowing(!following)}
                aria-pressed={!following}
                title={t("jr-pause-hint")}
              >
                {following ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
                {following ? t("jr-pause") : t("jr-resume")}
              </Button>
            )
          }
        />
        <div className="grid min-w-0 gap-4">
          <Chips
            label={t("jr-lanes")}
            items={LANE_IDS.map((id) => ({ id, label: t(`jr-lane-${id}`) }))}
            value={laneOf(search)}
            onChange={(lane) => set(inLane(search, lane))}
          />
          <div className="flex flex-wrap items-center gap-2">
            <SearchField ref={searchInput} search={search} onChange={set} />
            <PeriodPicker search={search} onChange={set} />
            {mobile ? <FilterSheet facets={facets.data} search={search} onChange={set} /> : null}
          </div>
          {mobile ? null : (
            <div className="flex flex-wrap items-center gap-2">
              <FilterBar facets={facets.data} search={search} onChange={set} />
            </div>
          )}
          <Histogram histogram={facets.data?.histogram} onRange={(from, to) => set({ ...search, from, to })} />
        </div>
      </div>
      <Stories
        key={JSON.stringify(filters)}
        search={search}
        following={following}
        open={(event) => onSearch({ ...search, event })}
      />
      <EventSheet position={search.event} onClose={() => onSearch({ ...search, event: undefined })} />
    </div>
  );
}

/** Where the journal stands: live, paused or a past period, and how many events the filters hold. */
function Edge({ following, live, facets }: { following: boolean; live: boolean; facets: JournalFacets | undefined }) {
  const t = useT();
  const { status } = useLive();
  return (
    <>
      {live ? (
        following && status === "open" ? (
          <Status tone="accent">{t("jr-now")}</Status>
        ) : (
          <Status tone="idle">{following ? t("jr-offline") : t("jr-paused")}</Status>
        )
      ) : null}
      {facets ? (
        <span aria-live="polite" className="tabular">
          {t("jr-event-count", { count: facets.total })}
        </span>
      ) : null}
    </>
  );
}

function Stories({
  search,
  following,
  open,
}: {
  search: JournalSearch;
  following: boolean;
  open: (position: number) => void;
}) {
  const t = useT();
  const { query, stories, queued, flush, isNew } = useJournal(filtersOf(search), following);
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query;

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasNextPage || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting) && !isFetchingNextPage) void fetchNextPage();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (query.isPending) return <Loading lines={5} label={t("jr-loading")} />;
  if (query.isError) return <Failure error={query.error} retry={() => void query.refetch()} />;

  return (
    <div className="grid min-w-0 gap-10">
      {queued.length ? (
        <Button variant="accent" className="justify-self-center rounded-full" onClick={flush}>
          <ArrowUp />
          {t("jr-new-events", { count: queued.length })}
        </Button>
      ) : null}
      {stories.length === 0 ? (
        <Empty hint={t("jr-empty-hint")}>{t("jr-empty")}</Empty>
      ) : (
        byDay(stories).map(([day, group]) => (
          <Section key={day} title={day.charAt(0).toUpperCase() + day.slice(1)} count={group.length}>
            <ol aria-label={t("jr-day-list", { day })} className="grid gap-3">
              {group.map((story) => (
                <li key={story.key} className="min-w-0">
                  <StoryCard
                    story={story}
                    open={open}
                    isNew={isNew}
                    unfolded={Boolean(search.conversation || search.session)}
                  />
                </li>
              ))}
            </ol>
          </Section>
        ))
      )}
      <div ref={sentinel} className="-mt-10" />
      {hasNextPage ? (
        <Button
          variant="outline"
          className="justify-self-center rounded-full"
          onClick={() => void fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? t("loading") : t("jr-older")}
        </Button>
      ) : stories.length ? (
        <p className="text-center text-[0.9rem] text-ink-muted">{t("jr-beginning")}</p>
      ) : null}
    </div>
  );
}

function byDay(stories: Story[]): [string, Story[]][] {
  const groups: [string, Story[]][] = [];
  for (const story of stories) {
    const day = dayLabel(story.latest);
    const last = groups.at(-1);
    if (last && last[0] === day) last[1].push(story);
    else groups.push([day, [story]]);
  }
  return groups;
}
