import { createFileRoute, useNavigate } from "@tanstack/react-router";
import type { MemoryQuery } from "@/api";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { MemoriesView } from "@/features/memories/memories-view";
import { useT } from "@/i18n";
import { useMe } from "@/lib/session";

const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);

export const Route = createFileRoute("/_app/memories")({
  validateSearch: (search: Record<string, unknown>): MemoryQuery => ({ q: text(search.q), about: text(search.about) }),
  component: Memories,
});

function Memories() {
  const query = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const me = useMe();
  const t = useT();
  return (
    <Guard scope="memories:read">
      <PageHeader title={t("mem-title")}>{t("mem-intro", { assistant: me.assistant })}</PageHeader>
      <MemoriesView query={query} onQuery={(next) => void navigate({ search: next, replace: true })} />
    </Guard>
  );
}
