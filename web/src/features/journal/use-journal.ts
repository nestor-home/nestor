import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { type JournalFilters, type JournalItem, journalQuery } from "@/api";
import { useLiveItems } from "@/features/shell/live";
import { matches, merge } from "./merge";
import { buildStories } from "./stories";

/**
 * The journal for some filters: pages loaded on demand, plus what the live stream brings, as
 * stories. While the person is not following, new events wait in `queued` instead of moving the
 * page. Mount it under a `key` made of the filters: changing them starts afresh.
 */
export function useJournal(filters: JournalFilters, following: boolean) {
  const query = useInfiniteQuery(journalQuery(filters));
  const [live, setLive] = useState<JournalItem[]>([]);
  const [queued, setQueued] = useState<JournalItem[]>([]);
  const arrived = useRef(new Set<string>());

  useLiveItems((item) => {
    if (!matches(item, filters)) return;
    arrived.current.add(item.id);
    if (following) setLive((lines) => [item, ...lines]);
    else setQueued((lines) => [item, ...lines]);
  });

  const flush = useCallback(() => {
    setLive((lines) => [...queued, ...lines]);
    setQueued([]);
  }, [queued]);

  const pages = query.data?.pages;
  const items = useMemo(() => merge(live, pages?.flatMap((p) => p.items) ?? []), [live, pages]);
  const stories = useMemo(() => buildStories(items), [items]);
  const isNew = useCallback((id: string) => arrived.current.has(id), []);

  return { query, items, stories, queued, flush, isNew };
}
