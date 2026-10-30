import { createFileRoute } from "@tanstack/react-router";
import { SatelliteOverview, useSatellite } from "@/features/satellites/satellite-detail";

export const Route = createFileRoute("/_app/satellites/$satelliteId/")({ component: Page });

function Page() {
  const { satelliteId } = Route.useParams();
  const { satellite } = useSatellite(satelliteId);
  return satellite ? <SatelliteOverview satellite={satellite} /> : null;
}
