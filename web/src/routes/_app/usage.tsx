import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { parseUsageSearch, type UsageSearch } from "@/features/usage/search";
import { UsageView } from "@/features/usage/usage-view";

export const Route = createFileRoute("/_app/usage")({
  validateSearch: (search: Record<string, unknown>): UsageSearch => parseUsageSearch(search),
  component: Usage,
});

function Usage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="usage:read">
      <UsageView search={search} onSearch={(next) => void navigate({ search: next, replace: true })} />
    </Guard>
  );
}
