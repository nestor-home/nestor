import { useQuery } from "@tanstack/react-query";
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { journalFacetsQuery } from "@/api";
import { Dither } from "@/components/dither";
import { Empty, Failure, Loading } from "@/components/states";
import { Kbd } from "@/components/status";
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
import { type Density, StoryCard } from "./story";
import { JournalToolbar } from "./toolbar";
import { useJournal } from "./use-journal";

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function JournalView({ search, onSearch }: { search: JournalSearch; onSearch: (next: JournalSearch) => void }) {
  const t = useT();
  const mobile = useIsMobile();
  const [following, setFollowing] = useState(true);
  const searchInput = useRef<HTMLInputElement>(null);
  const filters = filtersOf(search);
  const facets = useQuery(journalFacetsQuery(filters));
  const set = (next: JournalSearch) => onSearch(clean(next));

  // j/k between entries, / to search, p to pause: the journal reads like a pager
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
    <div className="grid gap-5">
      <JournalToolbar
        ref={searchInput}
        search={search}
        onChange={set}
        following={following}
        onFollowing={setFollowing}
      />
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {mobile ? (
          <FilterSheet facets={facets.data} search={search} onChange={set} />
        ) : (
          <FilterBar facets={facets.data} search={search} onChange={set} />
        )}
        <p className="flex items-center gap-4 font-mono text-[0.7rem] text-ink-muted">
          <span className="hidden items-center gap-1 text-ink-faint lg:flex">
            <Kbd>j</Kbd>
            <Kbd>k</Kbd>
            <span>{t("jr-keys-browse")}</span>
            <Kbd>/</Kbd>
            <span>{t("jr-keys-search")}</span>
            <Kbd>p</Kbd>
            <span>{t("jr-keys-pause")}</span>
          </span>
          {facets.data ? (
            <span aria-live="polite" className="tabular">
              {t("jr-event-count", { count: facets.data.total })}
            </span>
          ) : null}
        </p>
      </div>
      <Histogram histogram={facets.data?.histogram} onRange={(from, to) => set({ ...search, from, to })} />
      <Stories
        key={JSON.stringify(filters)}
        search={search}
        following={following}
        density={search.density ?? "comfortable"}
        open={(event) => onSearch({ ...search, event })}
      />
      <EventSheet id={search.event} onClose={() => onSearch({ ...search, event: undefined })} />
    </div>
  );
}

function Stories({
  search,
  following,
  density,
  open,
}: {
  search: JournalSearch;
  following: boolean;
  density: Density;
  open: (id: string) => void;
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

  const live = !search.to;
  return (
    <div>
      {live ? <NowMarker following={following} queued={queued.length} flush={flush} /> : null}
      {stories.length === 0 ? (
        <Empty hint={t("jr-empty-hint")}>{t("jr-empty")}</Empty>
      ) : (
        byDay(stories).map(([day, group]) => (
          <section key={day} aria-label={day} className="mb-8">
            <h2 className="sticky top-10 z-[1] mb-2 flex items-center gap-3 bg-paper/95 py-1.5 font-mono text-[0.72rem] text-ink-muted backdrop-blur-[2px]">
              <span className="first-letter:uppercase">{day}</span>
              <span aria-hidden="true" className="h-px flex-1 bg-rule" />
              <span className="tabular">{t("jr-story-count", { count: group.length })}</span>
            </h2>
            <ol
              aria-label={t("jr-day-list", { day })}
              className={density === "compact" ? "grid gap-1.5" : "grid gap-3"}
            >
              {group.map((story) => (
                <li key={story.key}>
                  <StoryCard story={story} density={density} open={open} isNew={isNew} />
                </li>
              ))}
            </ol>
          </section>
        ))
      )}
      <div ref={sentinel} />
      {hasNextPage ? (
        <Button variant="outline" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? t("loading") : t("jr-older")}
        </Button>
      ) : stories.length ? (
        <p className="py-4 text-center font-mono text-xs text-ink-faint">{t("jr-beginning")}</p>
      ) : null}
    </div>
  );
}

/** The live edge of the journal: where new events land, and how many wait while paused. */
function NowMarker({ following, queued, flush }: { following: boolean; queued: number; flush: () => void }) {
  const t = useT();
  const { status } = useLive();
  return (
    <div className="mb-5 flex items-center gap-3">
      <span className="inline-flex items-center gap-2 font-mono text-[0.72rem] text-ember">
        <span
          aria-hidden="true"
          className={
            following && status === "open"
              ? "live-dot size-1.5 rounded-full bg-ember"
              : "size-1.5 rounded-full border border-ember"
          }
        />
        {following ? t("jr-now") : t("jr-paused")}
      </span>
      <Dither shape="ramp-left" from={0.6} to={0} className="h-2 flex-1 text-ember/70" />
      {queued ? (
        <Button variant="accent" size="sm" onClick={flush}>
          <ArrowUp />
          {t("jr-new-events", { count: queued })}
        </Button>
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
