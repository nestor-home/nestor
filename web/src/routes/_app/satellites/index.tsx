import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { AddSatelliteButton } from "@/features/satellites/add-satellite";
import { SatellitesList } from "@/features/satellites/satellites-list";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";

export const Route = createFileRoute("/_app/satellites/")({
  validateSearch: (search: Record<string, unknown>): { approve?: string } =>
    typeof search.approve === "string" && search.approve ? { approve: search.approve } : {},
  component: Satellites,
});

function Satellites() {
  const t = useT();
  const { approve } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const canPair = useCan("satellites:write");
  return (
    <Guard scope="satellites:read">
      <PageHeader title={t("sat-title")} actions={canPair ? <AddSatelliteButton /> : undefined} />
      <SatellitesList approving={approve} onApprove={(id) => void navigate({ search: id ? { approve: id } : {} })} />
    </Guard>
  );
}
