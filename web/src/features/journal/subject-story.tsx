import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { type JournalFilters, journalLatestQuery } from "@/api";
import { Empty, Failure, Loading } from "@/components/states";
import { EventSheet } from "./event-sheet";
import { buildStories } from "./stories";
import { StoryCard } from "./story";

/** The journal's stories about one subject (a task, a watch, a person's conversations), in place. */
export function SubjectStory({
  filters,
  empty,
  limit = 200,
}: {
  filters: JournalFilters;
  empty: string;
  limit?: number;
}) {
  const latest = useQuery(journalLatestQuery(filters, limit));
  const [open, setOpen] = useState<string | undefined>();
  if (latest.isPending) return <Loading lines={3} />;
  if (latest.isError) return <Failure error={latest.error} retry={() => void latest.refetch()} />;
  const stories = buildStories(latest.data.items);
  if (stories.length === 0) return <Empty>{empty}</Empty>;
  return (
    <>
      <ol className="grid gap-3">
        {stories.map((story) => (
          <li key={story.key}>
            <StoryCard story={story} density="comfortable" open={setOpen} isNew={() => false} />
          </li>
        ))}
      </ol>
      <EventSheet id={open} onClose={() => setOpen(undefined)} />
    </>
  );
}
