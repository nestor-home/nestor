import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { JournalView } from "@/features/journal/journal-view";
import { type JournalSearch, parseJournalSearch } from "@/features/journal/search";

export const Route = createFileRoute("/_app/journal")({
  validateSearch: (search: Record<string, unknown>): JournalSearch => parseJournalSearch(search),
  component: Journal,
});

function Journal() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="journal:read">
      <JournalView search={search} onSearch={(next) => void navigate({ search: next, replace: !("event" in next) })} />
    </Guard>
  );
}
