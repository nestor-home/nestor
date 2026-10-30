import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { JournalView } from "@/features/journal/journal-view";
import { type JournalSearch, parseJournalSearch } from "@/features/journal/search";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/journal")({
  validateSearch: (search: Record<string, unknown>): JournalSearch => parseJournalSearch(search),
  component: Journal,
});

function Journal() {
  const t = useT();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="journal:read">
      <PageHeader title={t("jr-title")}>{t("jr-intro")}</PageHeader>
      <JournalView search={search} onSearch={(next) => void navigate({ search: next, replace: !("event" in next) })} />
    </Guard>
  );
}
