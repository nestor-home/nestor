import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { SatellitesView } from "@/features/satellites/satellites-list";

export const Route = createFileRoute("/_app/satellites/")({
  validateSearch: (search: Record<string, unknown>): { approve?: string } =>
    typeof search.approve === "string" && search.approve ? { approve: search.approve } : {},
  component: Satellites,
});

function Satellites() {
  const { approve } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <Guard scope="satellites:read">
      <SatellitesView approving={approve} onApprove={(id) => void navigate({ search: id ? { approve: id } : {} })} />
    </Guard>
  );
}
