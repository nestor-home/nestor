import { createFileRoute, useNavigate } from "@tanstack/react-router";
import type { MemoryQuery } from "@/api";
import { Guard } from "@/components/guard";
import { MemoriesView } from "@/features/memories/memories-view";

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export const Route = createFileRoute("/_app/memories")({
  validateSearch: (search: Record<string, unknown>): MemoryQuery => ({ q: text(search.q), about: text(search.about) }),
  component: Memories,
});

function Memories() {
  const query = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="memories:read">
      <MemoriesView query={query} onQuery={(next) => void navigate({ search: next, replace: true })} />
    </Guard>
  );
}
