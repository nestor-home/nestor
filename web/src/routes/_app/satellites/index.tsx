import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { SatellitesList } from "@/features/satellites/satellites-list";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/satellites/")({
  validateSearch: (search: Record<string, unknown>): { approve?: string } =>
    typeof search.approve === "string" && search.approve ? { approve: search.approve } : {},
  component: Satellites,
});

function Satellites() {
  const t = useT();
  const { approve } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="satellites:read">
      <PageHeader title={t("sat-title")} />
      <SatellitesList approving={approve} onApprove={(id) => void navigate({ search: id ? { approve: id } : {} })} />
    </Guard>
  );
}
